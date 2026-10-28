import io,unittest,zipfile
from xml.etree import ElementTree as ET
from invoice_intelligence.persistence.xlsx import workbook
class ExcelTests(unittest.TestCase):
    def test_untrusted_values_are_text_not_formulas(self):
        value='=HYPERLINK("https://evil.test","click")'
        data=workbook([('Invoices',[['Supplier','Total'],[value,'120.00'],['A&B <supplier>','\x00ok']])])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for path in z.namelist():ET.fromstring(z.read(path))
            root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'));ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            self.assertEqual(root.findall('.//s:f',ns),[])
            self.assertIn(value,[n.text for n in root.findall('.//s:t',ns)])
            self.assertTrue(all(c.attrib['t']=='inlineStr' for c in root.findall('.//s:c',ns)))
