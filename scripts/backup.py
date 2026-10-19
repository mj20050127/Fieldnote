"""Portable Extended JSON backup; restore only into an empty, explicitly named DB."""
import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings

COLLECTIONS = ('users', 'surveys', 'responses')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--target')
    args = parser.parse_args()
    settings = Settings()
    client = MongoClient(settings.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    try:
        if args.restore:
            if not args.target or not args.target.startswith('fieldnote_restore_'):
                parser.error('Restore target must begin with fieldnote_restore_; existing databases are never overwritten.')
            target = client[args.target]
            if target.list_collection_names():
                parser.error('Restore target is not empty. Use a new database name.')
            manifest = json.loads((args.restore / 'manifest.json').read_text(encoding='utf-8'))
            if manifest.get('format_version') != 1:
                parser.error('Unsupported backup format.')
            for name in COLLECTIONS:
                source = args.restore / f'{name}.jsonl.gz'
                if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['collections'][name]['sha256']:
                    parser.error(f'Backup checksum mismatch: {name}')
            for name in COLLECTIONS:
                rows = []
                count = 0
                with gzip.open(args.restore / f'{name}.jsonl.gz', 'rt', encoding='utf-8') as stream:
                    for line in stream:
                        rows.append(json_util.loads(line))
                        if len(rows) == 100:
                            target[name].insert_many(rows)
                            count += len(rows)
                            rows = []
                if rows:
                    target[name].insert_many(rows)
                    count += len(rows)
                if count != manifest['collections'][name]['count']:
                    raise RuntimeError(f'Unexpected record count in {name}; keep target for diagnosis.')
            print(f'Restored business data into {args.target}. Sessions were intentionally excluded.')
            print('Start the app with this MONGO_DATABASE to install validators and indexes, then verify it.')
        else:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            output = args.output or Path('.local/backups') / stamp
            output.mkdir(parents=True, exist_ok=False)
            db = client[settings.mongo_database]
            manifest = {'format_version': 1, 'created_at': stamp, 'collections': {}}
            for name in COLLECTIONS:
                destination = output / f'{name}.jsonl.gz'
                count = 0
                with gzip.open(destination, 'wt', encoding='utf-8') as stream:
                    for document in db[name].find({}):
                        stream.write(json_util.dumps(document, ensure_ascii=False) + '\n')
                        count += 1
                manifest['collections'][name] = {'count': count, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
            (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'Backup created: {output.resolve()}')
            print(json.dumps({name: record['count'] for name, record in manifest['collections'].items()}))
    finally:
        client.close()


if __name__ == '__main__':
    main()
