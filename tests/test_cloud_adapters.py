"""Offline checks for cloud SQL compatibility and immutable source boundaries."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from invoice_intelligence.cloud.postgres import translate,schema_sql,Row,PostgresStore
from invoice_intelligence.config import Settings
from invoice_intelligence.domain.errors import DocumentError

class CloudAdapterTests(unittest.TestCase):
    def test_bind_markers_and_nullable_job_target(self):
        self.assertEqual(translate('SELECT * FROM jobs WHERE (? IS NULL OR document_id=?)'),
            'SELECT * FROM jobs WHERE (CAST(%s AS TEXT) IS NULL OR document_id=%s)')
    def test_ignore_insert_and_stable_tie_order(self):
        self.assertEqual(translate('INSERT OR IGNORE INTO idempotency_keys VALUES (?,?,?)'),
            'INSERT INTO idempotency_keys VALUES (%s,%s,%s) ON CONFLICT DO NOTHING')
        self.assertIn('r.id DESC',translate('SELECT r.* FROM extraction_runs r ORDER BY r.created_at DESC,r.rowid DESC'))
    def test_schema_preserves_precision_and_foreign_keys(self):
        schema=schema_sql()
        self.assertNotIn('PRAGMA',schema);self.assertNotIn('RAISE(ABORT',schema)
        self.assertIn('DOUBLE PRECISION',schema);self.assertIn('REFERENCES documents(id)',schema)
    def test_row_supports_aggregate_index_and_named_fields(self):
        row=Row({'max':23});self.assertEqual(row[0],23);self.assertEqual(row['max'],23)
    def test_artifact_keys_cannot_escape_private_cache(self):
        with TemporaryDirectory() as folder:
            store=object.__new__(PostgresStore);store.settings=Settings(data_dir=Path(folder))
            for key in ['../.env','/etc/passwd','a/../../.env','a//b','a\\b']:
                with self.assertRaises(DocumentError):store._key(key)
            key,path=store._key('objects/synthetic.pdf');self.assertTrue(path.is_relative_to(Path(folder).resolve()));self.assertEqual(key,'objects/synthetic.pdf')

if __name__=='__main__':unittest.main()
