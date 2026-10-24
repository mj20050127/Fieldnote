"""Resumable Stage 1 snapshots -> Stage 2 identities. Stop application writers before --apply."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.database import initialize_database
from backend.app.library import content_of, digest, stable_id, validate_content
from backend.app.errors import BusinessError
from backend.app.repositories import utcnow


async def migrate(db, apply=False):
    report = {'database': db.name, 'mode': 'apply' if apply else 'dry-run', 'updated_surveys': 0,
              'linked_questions': 0, 'already_linked': 0, 'skipped': [], 'conflicts': []}
    async for survey in db.surveys.find({}).sort('_id', 1):
        questions = []
        changed = False
        for question in survey['questions']:
            if question.get('source'):
                report['already_linked'] += 1
                questions.append(question)
                continue
            try:
                content = content_of(question)
                validate_content(content)
            except (ValidationError, BusinessError) as error:
                report['skipped'].append({'survey_id': survey['_id'], 'question_id': question['id'], 'reason': str(error)})
                questions.append(question)
                continue
            uid = survey['owner_id']
            bid = stable_id(f'legacy-bank:{uid}')
            qid = stable_id(f'legacy-question:{survey["_id"]}:{question["id"]}')
            vid = stable_id(f'legacy-version:{survey["_id"]}:{question["id"]}')
            now = utcnow()
            if apply:
                await db.question_banks.update_one({'_id': bid}, {'$setOnInsert': {
                    '_id': bid, 'owner_id': uid, 'name': '第一阶段迁移题库', 'description': '原有问卷题目，按原题位分别保留。',
                    'revision': 1, 'archived': False, 'created_at': now, 'updated_at': now}}, upsert=True)
                fingerprint = digest({'legacy': survey['_id'], 'instance_id': question['id'], 'content': content})
                await db.questions.update_one({'_id': qid}, {'$setOnInsert': {
                    '_id': qid, 'owner_id': uid, 'bank_id': bid, 'shared_with': [], 'version_counter': 1,
                    'revision': 1, 'archived': False, 'status': 'creating', 'derived_from': None,
                    'creation_hash': fingerprint, 'created_at': now, 'updated_at': now}}, upsert=True)
                existing = await db.questions.find_one({'_id': qid})
                if existing['creation_hash'] != fingerprint:
                    raise RuntimeError('Legacy content changed during migration; keep maintenance mode and investigate.')
                try:
                    await db.question_versions.insert_one({'_id': vid, 'question_id': qid, 'version_no': 1,
                        'parent_version_id': None, 'restored_from_version_id': None, 'content': content,
                        'created_by': uid, 'request_id': 'migration_' + vid, 'payload_hash': fingerprint,
                        'created_at': survey['created_at']})
                except DuplicateKeyError:
                    version = await db.question_versions.find_one({'_id': vid})
                    if not version or version['content'] != content:
                        raise RuntimeError('Migration version conflict; restore the pre-migration backup.')
                await db.questions.update_one({'_id': qid}, {'$set': {'status': 'active'}})
            questions.append(question | {'source': {'question_id': qid, 'version_id': vid}})
            changed = True
            report['linked_questions'] += 1
        if changed:
            if apply:
                result = await db.surveys.update_one({'_id': survey['_id'], 'revision': survey['revision']},
                    {'$set': {'questions': questions, 'schema_version': 2}, '$inc': {'revision': 1}})
                if not result.matched_count:
                    report['conflicts'].append(survey['_id'])
                    raise RuntimeError('Concurrent survey write detected; keep maintenance mode and rerun after diagnosis.')
            report['updated_surveys'] += 1
    return report


async def run(args):
    settings = Settings()
    client = AsyncMongoClient(settings.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    try:
        db = client[args.database or settings.mongo_database]
        if args.apply:
            if not args.maintenance:
                raise SystemExit('--apply requires --maintenance: stop all application writers first.')
            if not args.backup or not (args.backup / 'manifest.json').is_file():
                raise SystemExit('--apply requires --backup pointing to a verified pre-migration backup.')
            from bson import json_util
            import gzip
            import hashlib
            manifest = json.loads((args.backup / 'manifest.json').read_text(encoding='utf-8'))
            for name, record in manifest['collections'].items():
                source = args.backup / f'{name}.jsonl.gz'
                if hashlib.sha256(source.read_bytes()).hexdigest() != record['sha256']:
                    raise SystemExit('Backup checksum mismatch: ' + name)
            # Only metadata is changed. A backup from another project must not qualify.
            with gzip.open(args.backup / 'surveys.jsonl.gz', 'rt', encoding='utf-8') as stream:
                backup_ids = {json_util.loads(line)['_id'] for line in stream}
            current_ids = set(await db.surveys.distinct('_id'))
            if backup_ids != current_ids:
                raise SystemExit('Backup survey identities do not match the target database.')
            await initialize_database(db)
        report = await migrate(db, args.apply)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        await client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--maintenance', action='store_true')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--report', type=Path, default=Path('.local/stage2-migration.json'))
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error('Choose either --dry-run or --apply.')
    asyncio.run(run(args))
