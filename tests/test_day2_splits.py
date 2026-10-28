"""Optional local corpus checks; skip cleanly when dataset is not downloaded."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / 'data/splits/invoicebenchmark/test.json').exists(), 'Run prepare_day2.py with downloaded dataset')
class SplitIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.manifests = {name: json.loads((ROOT / f'data/splits/invoicebenchmark/{name}.json').read_text())
            for name in ['development', 'calibration', 'test']}

    def test_exhaustive_disjoint_document_and_supplier_groups(self):
        ids, suppliers = set(), set()
        for manifest in self.manifests.values():
            group_ids = {r['document_id'] for r in manifest['documents']}
            group_suppliers = {r['supplier_group'] for r in manifest['documents']}
            self.assertTrue(ids.isdisjoint(group_ids))
            self.assertTrue(suppliers.isdisjoint(group_suppliers))
            ids |= group_ids
            suppliers |= group_suppliers
        self.assertEqual(len(ids), 200)
        self.assertEqual(len(suppliers), 32)

    def test_frozen_manifest_and_source_hashes_match(self):
        summary = json.loads((ROOT / 'docs/day2/split_summary.json').read_text())
        for name, manifest in self.manifests.items():
            path = ROOT / f'data/splits/invoicebenchmark/{name}.json'
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), summary['manifests'][name])
            for record in manifest['documents']:
                for kind, relative in record['paths'].items():
                    self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), record['sha256'][kind])

    def test_inspection_sample_stays_in_development(self):
        sample = json.loads((ROOT / 'data/splits/invoicebenchmark/inspection_sample.json').read_text())['document_ids']
        development = {r['document_id'] for r in self.manifests['development']['documents']}
        self.assertEqual(len(set(sample)), 20)
        self.assertTrue(set(sample) <= development)
