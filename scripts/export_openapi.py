"""Export the actual FastAPI schemas without connecting to MongoDB."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.main import app

destination = ROOT / 'frontend' / 'openapi.json'
destination.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Exported {len(app.openapi()["paths"])} API paths.')
