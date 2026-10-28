"""Strict, bounded CSV input. Parsing completes before any database write."""
import csv
from decimal import Decimal, InvalidOperation
import io
import re
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.matching.rules import digest, normalize

MAX_CSV_BYTES=1024*1024
COLUMNS=['po_number','supplier_name','currency','line_number','sku','description','quantity','unit_price']
TEMPLATE=','.join(COLUMNS)+'\nPO-DEMO-001,Example Supplier,EUR,1,PAPER-A,Paper cartons,2,50.00\n'


def parse_csv(raw):
    if not raw or len(raw)>MAX_CSV_BYTES:
        raise DocumentError('invalid_po_csv','Provide a nonempty UTF-8 CSV of at most 1 MiB.',422)
    try:
        text=raw.decode('utf-8-sig')
        reader=csv.DictReader(io.StringIO(text),strict=True)
        if reader.fieldnames!=COLUMNS:
            raise ValueError('CSV headers and order must be: '+','.join(COLUMNS))
        orders={}
        count=0
        for row in reader:
            count+=1
            if count>1000: raise ValueError('At most 1000 item rows may be imported at once.')
            if None in row or any(v is None for v in row.values()): raise ValueError(f'CSV row {reader.line_num} has the wrong number of cells.')
            row={k:v.strip() for k,v in row.items()}
            if any(len(v)>1000 or '\x00' in v for v in row.values()): raise ValueError('Cells must be at most 1000 characters and contain no NUL.')
            if not all(row[k] for k in ['po_number','supplier_name','currency','line_number','description']): raise ValueError('PO reference, supplier, currency, line number and description are required.')
            if not normalize(row['supplier_name']) or not normalize(row['description']): raise ValueError('Supplier and description must contain letters or digits.')
            if not re.fullmatch('[A-Z]{3}',row['currency']): raise ValueError('Currency must be three uppercase letters.')
            key=normalize(row['po_number'])
            if not key: raise ValueError('PO number must contain letters or digits.')
            for name in ['quantity','unit_price']:
                raw_value=row[name]
                if not re.fullmatch(r'\d{1,13}(?:\.\d{1,6})?',raw_value): raise ValueError(f'{name} must be a plain decimal (up to six decimal places, no separators).')
                amount=Decimal(raw_value)
                if amount>Decimal('1e12') or (amount<=0 if name=='quantity' else amount<0): raise ValueError(f'{name} is outside the supported range.')
                row[name]=format(amount.normalize(),'f')
            header={k:row[k] for k in ['po_number','supplier_name','currency']}
            if key not in orders: orders[key]=header|{'lines':[]}
            order=orders[key]
            if any(order[k]!=header[k] for k in header): raise ValueError('A PO must have one consistent reference, supplier and currency.')
            if any(normalize(line['line_number'])==normalize(row['line_number']) for line in order['lines']): raise ValueError('Line numbers must be unique within a PO.')
            if not normalize(row['line_number']): raise ValueError('Line number must contain letters or digits.')
            order['lines'].append({k:row[k] for k in ['line_number','sku','description','quantity','unit_price']})
        if not orders: raise ValueError('CSV contains no item rows.')
        if len(orders)>100: raise ValueError('At most 100 POs may be imported at once.')
        for order in orders.values():
            order['lines'].sort(key=lambda line:line['line_number'])
            order['content_digest']=digest(order)
        return orders
    except (UnicodeError,csv.Error,ValueError,InvalidOperation) as error:
        raise DocumentError('invalid_po_csv',str(error),422) from None
