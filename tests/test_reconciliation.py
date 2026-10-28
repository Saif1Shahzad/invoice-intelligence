import unittest
from decimal import Decimal as D

from invoice_intelligence.domain.reconciliation import reconcile


class ReconciliationTests(unittest.TestCase):
    def check_invoice(self, **changes):
        args = dict(line_nets=[D("100"), D("50")], subtotal=D("150"),
                    discount=D("10"), shipping=D("5"), tax=D("14"), total=D("159"))
        args.update(changes)
        return reconcile(**args)

    def test_discount_shipping_tax_reconcile(self):
        self.assertEqual(self.check_invoice(), [])

    def test_detects_both_header_mismatches(self):
        issues = self.check_invoice(subtotal=D("149"), total=D("160"))
        self.assertEqual([x["code"] for x in issues], ["subtotal_mismatch", "total_mismatch"])

    def test_tolerance_boundary(self):
        self.assertEqual(self.check_invoice(total=D("159.01")), [])
        self.assertEqual(self.check_invoice(total=D("159.02"))[0]["code"], "total_mismatch")

    def test_currency_tolerance_can_be_zero(self):
        self.assertTrue(self.check_invoice(total=D("159.01"), tolerance=D("0")))

    def test_missing_rows_are_not_a_pass(self):
        self.assertEqual(self.check_invoice(line_nets=[])[0]["code"], "missing_line_items")

    def test_invalid_numeric_inputs_fail(self):
        for changes in ({"tax": D("NaN")}, {"tolerance": D("-0.01")}):
            with self.assertRaises(ValueError):
                self.check_invoice(**changes)


if __name__ == "__main__":
    unittest.main()
