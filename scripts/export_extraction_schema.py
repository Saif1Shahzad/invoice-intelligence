"""Export the current Pydantic contract as JSON Schema; run in the project venv."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from invoice_intelligence.schemas.extraction import InvoiceExtraction

path = root / 'docs/day2/extraction.schema.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(InvoiceExtraction.model_json_schema(), indent=2) + '\n')
print(path)
