"""Restore a backup into an isolated DB, check counts/API/statistics, then clean it up."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from pymongo import MongoClient
from backend.app.config import Settings
from backend.app.main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('backup', type=Path)
    args = parser.parse_args()
    settings = Settings()
    target = 'fieldnote_restore_verification_' + uuid4().hex
    subprocess.run([sys.executable, str(Path(__file__).with_name('backup.py')), '--restore', str(args.backup), '--target', target], check=True)
    client = MongoClient(settings.mongo_uri, tz_aware=True)
    try:
        manifest = json.loads((args.backup / 'manifest.json').read_text(encoding='utf-8'))
        counts = {name: client[target][name].count_documents({}) for name in manifest['collections']}
        assert counts == {name: row['count'] for name, row in manifest['collections'].items()}
        with TestClient(create_app(Settings(mongo_database=target, app_env='test'))) as http:
            assert http.get('/api/health').status_code == 200
            account = http.post('/api/auth/login', json={'username': 'demo', 'password': 'Fieldnote2026!'})
            assert account.status_code == 200
            surveys = http.get('/api/surveys').json()['items']
            survey = next(s for s in surveys if s['title'] == '校园学习空间体验调查')
            stats = http.get(f'/api/surveys/{survey["id"]}/statistics').json()
            assert stats['total_responses'] == 3
            assert next(q for q in stats['questions'] if q['question_id'] == 'hours')['average'] == 15
        plan = client[target].responses.find({'survey_id': survey['id']}).sort('submitted_at', -1).explain()
        evidence = {'restored_counts': counts, 'statistics_average': 15,
                    'query_plan': plan['queryPlanner']['winningPlan']}
        output = Path('.local/backup-verification.json')
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False))
    finally:
        assert target.startswith('fieldnote_restore_verification_')
        client.drop_database(target)
        client.close()


if __name__ == '__main__':
    main()
