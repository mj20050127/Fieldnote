import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from pymongo import AsyncMongoClient, MongoClient

from backend.app.config import Settings
from scripts.backup import FORMATS
from scripts.migrate_stage2 import migrate
from conftest import create_published, register, submission


def migration(database, apply):
    async def run():
        client = AsyncMongoClient(Settings().mongo_uri, tz_aware=True)
        try:
            return await migrate(client[database], apply)
        finally:
            await client.close()
    return asyncio.run(run())


def test_migration_dry_run_resume_preserves_submissions_and_revision(environment):
    c, db = environment
    register(c)
    survey = create_published(c, allow_multiple=True)
    request = submission(value=8)
    receipt = c.post(f'/api/forms/{survey["public_code"]}/responses', json=request).json()
    draft = c.post('/api/surveys', json={'questions': [{'id': 'unfinished', 'type': 'text', 'title': ''}]}).json()
    db.surveys.update_many({}, {'$set': {'schema_version': 1}})
    before = db.surveys.find_one({'_id': survey['id']})
    responses = list(db.responses.find({}))
    stats_before = c.get(f'/api/surveys/{survey["id"]}/statistics').json()
    dry = migration(db.name, False)
    assert dry['linked_questions'] == 1 and len(dry['skipped']) == 1
    assert db.questions.count_documents({}) == 0
    applied = migration(db.name, True)
    assert applied['updated_surveys'] == 1
    after = db.surveys.find_one({'_id': survey['id']})
    for key in before:
        if key not in ('revision', 'schema_version', 'questions'):
            assert before[key] == after[key]
    assert before['questions'][0] == after['questions'][0] | {'source': None}
    assert after['revision'] == before['revision'] + 1 and after['schema_version'] == 2
    assert list(db.responses.find({})) == responses
    assert c.get(f'/api/surveys/{survey["id"]}/statistics').json() == stats_before
    replay = c.post(f'/api/forms/{survey["public_code"]}/responses', json=request)
    assert replay.status_code == 200 and replay.json()['id'] == receipt['id']
    rerun = migration(db.name, True)
    assert rerun['linked_questions'] == 0 and db.questions.count_documents({}) == 1
    # Simulate an interruption after v1 activation but before the survey source CAS.
    db.surveys.replace_one({'_id': survey['id']}, before)
    migration(db.name, True)
    assert db.question_versions.count_documents({}) == 1
    assert db.surveys.find_one({'_id': draft['id']})['questions'][0]['source'] is None


def test_equal_legacy_titles_remain_distinct_and_stale_editor_conflicts(environment):
    c, db = environment
    register(c)
    first = create_published(c)
    second = create_published(c)
    draft = c.post('/api/surveys', json={'questions': first['questions']}).json()
    report = migration(db.name, True)
    assert report['linked_questions'] == 3
    assert db.questions.count_documents({}) == 3
    assert db.question_versions.count_documents({}) == 3
    assert c.put(f'/api/surveys/{draft["id"]}/definition', json={'title': '旧窗口', 'questions': first['questions'], 'expected_revision': 1}).status_code == 409


def test_backup_both_formats_restorable_with_checksums(environment, tmp_path):
    c, db = environment
    register(c)
    create_published(c)
    migration(db.name, True)
    env = os.environ | {'MONGO_DATABASE': db.name}
    script = str(Path(__file__).resolve().parents[2] / 'scripts/backup.py')
    folder = tmp_path / 'backup'
    subprocess.run([sys.executable, script, '--output', str(folder)], env=env, check=True, capture_output=True)
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['format_version'] == 2 and set(manifest['collections']) == set(FORMATS[2])
    connection = MongoClient(Settings().mongo_uri)
    targets = []
    try:
        for format_version in (2, 1):
            if format_version == 1:
                manifest['format_version'] = 1
                manifest['collections'] = {k: v for k,v in manifest['collections'].items() if k in FORMATS[1]}
                (folder / 'manifest.json').write_text(json.dumps(manifest))
            target = 'fieldnote_restore_test_' + uuid4().hex
            targets.append(target)
            subprocess.run([sys.executable, script, '--restore', str(folder), '--target', target], env=env, check=True, capture_output=True)
            for name in FORMATS[format_version]:
                assert connection[target][name].count_documents({}) == db[name].count_documents({})
        with open(folder / 'surveys.jsonl.gz', 'ab') as stream:
            stream.write(b'corrupted')
        target = 'fieldnote_restore_test_' + uuid4().hex
        targets.append(target)
        result = subprocess.run([sys.executable, script, '--restore', str(folder), '--target', target], env=env, capture_output=True)
        assert result.returncode != 0 and b'checksum' in result.stderr
        assert connection[target].list_collection_names() == []
    finally:
        for name in targets:
            assert name.startswith('fieldnote_restore_test_')
            connection.drop_database(name)
        connection.close()
