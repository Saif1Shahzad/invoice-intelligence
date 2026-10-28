"""Export only confirmed records whose live matching context remains accepted."""
import csv
import io
import json
from invoice_intelligence.domain.errors import DocumentError
from invoice_intelligence.persistence.matching import MatchingStore

class ExportStore:
    def __init__(self,base): self.base=base

    def approved(self,document_id=None):
        with self.base.transaction() as c:
            snapshot=MatchingStore(self.base).profiles(c)
            rows=c.execute('''SELECT r.* FROM review_heads h JOIN review_revisions r ON
                r.document_id=h.document_id AND r.revision=h.revision WHERE r.status='approved'
                ORDER BY r.document_id''').fetchall()
            records=[];excluded=[]
            for row in rows:
                if document_id is not None and row['document_id']!=document_id: continue
                if row['document_id'] not in snapshot[0]:
                    excluded.append(row['document_id']);continue
                findings=MatchingStore(self.base).findings(c,row['document_id'],snapshot)
                saved=next((x['after'] for x in json.loads(row['changes_json']) if x['field']=='matching_checks'),None)
                if not saved or saved['token']!=findings['token'] or not findings['allowed']:
                    excluded.append(row['document_id']);continue
                records.append({'document_id':row['document_id'],'revision':row['revision'],
                    'source_run_id':row['source_run_id'],'confirmed_at':row['created_at'],'reviewer':row['actor'],
                    'reason':row['reason'],'fields':json.loads(row['fields_json']),
                    'validation':json.loads(row['validation_json']),'decision_checks':saved})
        if document_id is not None and not records:
            raise DocumentError('export_not_allowed','Only a confirmed invoice with unchanged accepted matching checks can be exported. Reload/reopen review if needed.',409)
        return {'records':records,'excluded_stale_confirmations':excluded,
                'scope':'Local reviewed records; no accounting posting or payment.'}

    def csv(self):
        result=self.approved();out=io.StringIO();writer=csv.writer(out)
        writer.writerow(['document_id','review_revision','supplier','invoice_number','issue_date','currency','subtotal','tax','total','shipping','tip','service_fee','previous_balance','amount_paid','amount_due','line_number','description','quantity','unit_price','line_amount','reviewer'])
        def safe(value):
            text='' if value is None else str(value)
            # CSV text must not execute as spreadsheet formulas when opened in Excel.
            return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
        for record in result['records']:
            fields=record['fields']
            def v(name):return fields.get(name,{}).get('value')
            for i,line in enumerate(fields['line_items'],1):
                writer.writerow([safe(record['document_id']),record['revision'],safe(v('supplier_name')),safe(v('invoice_number')),
                    safe(v('issue_date')),safe(v('currency')),v('subtotal'),v('tax_amount'),v('total'),v('shipping'),v('tip'),v('service_fee'),v('previous_balance'),v('amount_paid'),v('amount_due'),i,
                    safe(line['description']['value']),line['quantity']['value'],line['unit_price']['value'],line['amount']['value'],safe(record['reviewer'])])
        return out.getvalue(),len(result['records']),len(result['excluded_stale_confirmations'])
