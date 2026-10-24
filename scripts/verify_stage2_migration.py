"""Restore, migrate twice, and verify snapshot/response/API compatibility in an isolated database."""
import argparse
import asyncio
import json
import secrets
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from bson import json_util
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient, MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.auth import token_hash
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repositories import utcnow
from scripts.migrate_stage2 import migrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--report', type=Path, default=Path('.local/stage2-migration-verification.json'))
    args = parser.parse_args()
    target = 'fieldnote_restore_stage2_' + uuid4().hex
    subprocess.run([sys.executable, str(Path(__file__).with_name('backup.py')), '--restore', str(args.backup), '--target', target], check=True)
    settings = Settings(mongo_database=target, app_env='test')
    client = MongoClient(settings.mongo_uri, tz_aware=True)
    db = client[target]
    try:
        before = list(db.surveys.find({}).sort('_id', 1))
        responses = list(db.responses.find({}).sort('_id', 1))
        async def run():
            connection = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
            try:
                database = connection[target]
                dry = await migrate(database, False)
                assert await database.questions.count_documents({}) == 0
                applied = await migrate(database, True)
                count = await database.question_versions.count_documents({})
                again = await migrate(database, True)
                assert again['linked_questions'] == 0 and await database.question_versions.count_documents({}) == count
                return dry, applied, count
            finally:
                await connection.close()
        with TestClient(create_app(settings)) as http:
            # Internal test sessions scoped to the disposable restore DB; no passwords in reports.
            def impersonate(uid):
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.sessions.insert_one({'_id': token_hash(token), 'user_id': uid, 'csrf_token': csrf,
                    'created_at': utcnow(), 'expires_at': utcnow() + timedelta(hours=1)})
                http.cookies.set(settings.cookie_name, token)
                http.headers['X-CSRF-Token'] = csrf
            previous_stats = {}
            for survey in before:
                impersonate(survey['owner_id'])
                previous_stats[survey['_id']] = http.get(f'/api/surveys/{survey["_id"]}/statistics').json()
            dry, applied, count = asyncio.run(run())
            assert list(db.responses.find({}).sort('_id', 1)) == responses
            for survey in before:
                after = db.surveys.find_one({'_id': survey['_id']})
                assert {k:v for k,v in survey.items() if k not in ('questions','revision','schema_version')} == {
                    k:v for k,v in after.items() if k not in ('questions','revision','schema_version')}
                assert [{k:v for k,v in q.items() if k != 'source'} for q in survey['questions']] == [
                    {k:v for k,v in q.items() if k != 'source'} for q in after['questions']]
                impersonate(survey['owner_id'])
                assert http.get(f'/api/surveys/{survey["_id"]}/statistics').json() == previous_stats[survey['_id']]
            for response in responses:
                survey = db.surveys.find_one({'_id': response['survey_id']})
                impersonate(response['respondent_id'])
                payload = {k:response[k] for k in ('request_id','definition_version','is_anonymous','answers')}
                result = http.post(f'/api/forms/{survey["public_code"]}/responses', json=payload)
                assert result.status_code == 200, result.text
                assert result.json()['id'] == response['_id'] and result.json()['replayed']
        evidence = {'source_format': json.loads((args.backup/'manifest.json').read_text())['format_version'],
            'survey_count': len(before), 'response_count': len(responses), 'linked_questions': applied['linked_questions'],
            'version_count_after_rerun': count, 'skipped_incomplete': len(dry['skipped']), 'snapshots_unchanged': True,
            'response_documents_unchanged': True, 'statistics_unchanged': True, 'submission_replays_passed': len(responses),
            'dry_run_no_writes': True, 'repeat_no_duplicates': True}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    finally:
        assert target.startswith('fieldnote_restore_stage2_')
        client.drop_database(target)
        client.close()


if __name__ == '__main__':
    main()
