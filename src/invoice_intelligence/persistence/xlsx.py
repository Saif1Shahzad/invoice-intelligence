"""Small dependency-free Excel workbook; all untrusted values are text cells."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import re

def workbook(sheets):
    out=BytesIO()
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    def col(n):
        s=''
        while n:n,r=divmod(n-1,26);s=chr(65+r)+s
        return s
    def clean(v):return escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(v if v is not None else ''))[:32767])
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        types+=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>'
        z.writestr('[Content_Types].xml',types)
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        for i,(_,rows) in enumerate(sheets,1):
            data=''.join(f'<row r="{r}">'+''.join(f'<c r="{col(c)}{r}" t="inlineStr"><is><t xml:space="preserve">{clean(v)}</t></is></c>' for c,v in enumerate(row,1))+'</row>' for r,row in enumerate(rows,1))
            z.writestr(f'xl/worksheets/sheet{i}.xml',f'<worksheet xmlns="{ns}"><sheetData>{data}</sheetData></worksheet>')
    return out.getvalue()

def confirmed_workbook(store):
    from invoice_intelligence.persistence.exports import ExportStore
    records=ExportStore(store).approved()['records']
    keys=['supplier_name','invoice_number','issue_date','currency','subtotal','tax_amount','total']
    invoices=[['Document ID','Review revision',*keys,'Reviewer']]
    items=[['Document ID','Line','Description','Quantity','Unit price','Amount']]
    for r in records:
        f=r['fields'];invoices.append([r['document_id'],r['revision'],*[f.get(k,{}).get('value') for k in keys],r['reviewer']])
        for n,line in enumerate(f.get('line_items',[]),1):items.append([r['document_id'],n,*[line.get(k,{}).get('value') for k in ['description','quantity','unit_price','amount']]])
    return workbook([('Invoices',invoices),('Line items',items)])
