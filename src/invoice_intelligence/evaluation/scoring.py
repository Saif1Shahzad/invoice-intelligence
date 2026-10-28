"""Frozen value normalization and positional row scoring, including failures/extras."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import unicodedata

CRITICAL=['supplier_name','invoice_number','issue_date','currency','tax_mode','subtotal','total']
NUMERIC={'subtotal','document_discount','shipping','tax_amount','tax_rate','total','conditional_discount_rate','quantity','unit_price','amount','discount_amount','rate'}

def same(predicted,expected,name):
    if predicted is None:return False
    if name in NUMERIC:
        try:return Decimal(str(predicted))==Decimal(str(expected))
        except InvalidOperation:return False
    def text(v):return ' '.join(unicodedata.normalize('NFKC',str(v)).split())
    return text(predicted)==text(expected)

def score(fields,labels):
    fields=fields or {};counts=defaultdict(int);by_field={};errors=[];critical=[]
    for name,target in labels['fields'].items():
        observed=fields.get(name,{})
        if target['score_extraction']:
            correct=bool(observed.get('status')=='observed' and same(observed.get('value'),target['value'],name))
            counts['header_total']+=1;counts['header_correct']+=correct
            by_field[name]={'correct':int(correct),'total':1}
            if not correct:errors.append({'field':name,'expected':target['value'],'observed':observed.get('value')})
            if name in CRITICAL:critical.append(correct)
        if target.get('score_absence'):
            counts['absence_total']+=1;counts['absence_correct']+=observed.get('value') is None
    counts['critical_assessable']=int(all(labels['fields'].get(n,{}).get('score_extraction') for n in CRITICAL))
    counts['critical_record_correct']=int(bool(counts['critical_assessable']) and all(critical))
    predicted=fields.get('line_items',[]);truth=labels['line_items']
    counts['expected_rows']=len(truth);counts['predicted_rows']=len(predicted)
    counts['missing_rows']=max(0,len(truth)-len(predicted));counts['extra_rows']=max(0,len(predicted)-len(truth))
    for index,row in enumerate(truth):
        exact=True;scored=False
        for name,target in row.items():
            if target['score_extraction']:
                scored=True;observed=predicted[index].get(name,{}) if index<len(predicted) else {}
                correct=bool(observed.get('status')=='observed' and same(observed.get('value'),target['value'],name))
                counts['cell_total']+=1;counts['cell_correct']+=correct;exact=exact and correct
                if not correct:errors.append({'field':f'line_items[{index}].{name}','expected':target['value'],'observed':observed.get('value')})
        counts['exact_rows']+=int(exact and scored)
    counts['cell_total']+=counts['extra_rows']*4
    counts['fully_scored_record_correct']=int(not errors and not counts['extra_rows'] and counts['absence_correct']==counts['absence_total'])
    for key in ['header_correct','header_total','absence_correct','absence_total','cell_correct','cell_total','exact_rows']:
        counts[key]+=0
    return {'counts':dict(counts),'fields':by_field,'errors':errors}

def readiness(record,threshold):
    fields=record.get('extraction',{}).get('fields') or {}
    if record.get('extraction',{}).get('validation',{}).get('routing')!='ready_for_confirmation':return False
    if not all(fields.get(n,{}).get('status')=='observed' and fields[n].get('evidence') for n in CRITICAL):return False
    scores=[p['mean_ocr_score'] for p in (record.get('result') or {}).get('pages',[]) if p.get('method')=='ocr']
    return not scores or (all(s is not None for s in scores) and min(scores)>=threshold)
