"""Explainable local matching rules. Similarities are heuristics, not probabilities."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import hashlib
import json
import unicodedata

VERSION = 'matching-v2'
REFERENCE_SIMILARITY = .88
SUPPLIER_SIMILARITY = .90
ITEM_SIMILARITY = .92


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()).hexdigest()


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',str(value or '')).casefold() if c.isalnum())


def value(fields, name):
    field = fields.get(name,{})
    return field.get('value') if field.get('status') in {'observed','corrected'} else None


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result.copy_abs() <= Decimal('1e24') else None
    except (InvalidOperation, ValueError):
        return None


def similar(a,b):
    return SequenceMatcher(None,a,b,autojunk=False).ratio() if a and b and max(len(a),len(b))<=4000 else 0


def duplicate_rule(a, b):
    """Input is value wrappers, not filenames, images or answer keys."""
    # Unverified vision values can raise a conservative duplicate HOLD, never clear one.
    def has_proposal(obj):
        if isinstance(obj,dict):return obj.get('status')=='proposed' or any(has_proposal(v) for v in obj.values())
        return isinstance(obj,list) and any(has_proposal(v) for v in obj)
    if has_proposal(a) or has_proposal(b):
        def candidates(obj):
            if isinstance(obj,dict):return {k:('observed' if k=='status' and v=='proposed' else candidates(v)) for k,v in obj.items()}
            if isinstance(obj,list):return [candidates(v) for v in obj]
            return obj
        result=duplicate_rule(candidates(a),candidates(b))
        if result:
            result['unverified_candidate']=True
            result['reasons'].append('Vision-only proposal contributed; verify both source documents before classification.')
        return result
    sa,sb = normalize(value(a,'supplier_name')),normalize(value(b,'supplier_name'))
    ra,rb = normalize(value(a,'invoice_number')),normalize(value(b,'invoice_number'))
    ca,cb = value(a,'currency'),value(b,'currency')
    da,db = value(a,'issue_date'),value(b,'issue_date')
    ta,tb = number(value(a,'total')),number(value(b,'total'))
    same_supplier = bool(sa and sa == sb)
    same_ref = bool(ra and ra == rb)
    same_date = bool(da and da == db)
    same_money = bool(ca and ca == cb and ta is not None and tb is not None and abs(ta-tb) <= (Decimal('1') if ca=='JPY' else Decimal('.01')))
    # Invoice vs credit note is a different business document even with reused references.
    kinds = [value(a,'document_type'),value(b,'document_type')]
    if all(kinds) and kinds[0] != kinds[1]:
        return None
    if same_supplier and same_ref:
        return {'rule':'supplier_and_reference', 'reasons':['Same normalized supplier and invoice number.',
            'Amounts/currency differ; inspect the discrepancy.' if not same_money else 'Currency and total also agree.']}
    # Distinct clean numeric references are hard negatives (e.g. sequential bills).
    # A fuzzy rule requires an OCR-like substitution, rather than any close number.
    confusable = str.maketrans({'o':'0','i':'1','l':'1','s':'5','b':'8'})
    fuzzy_ref = bool(ra and rb and ra != rb and len(ra)>=5 and len(rb)>=5 and
                     ra.translate(confusable)==rb.translate(confusable) and similar(ra,rb)>=REFERENCE_SIMILARITY)
    if same_money and same_date and ((same_supplier and fuzzy_ref) or
        (same_ref and similar(sa,sb)>=SUPPLIER_SIMILARITY)):
        return {'rule':'ocr_like_identity', 'reasons':['Invoice identity has an OCR-like difference.',
            'Supplier/reference similarity is supported by the same date, currency and total.']}
    if same_supplier and same_money and same_date and (not ra or not rb):
        def descriptions(fields):
            return sorted(normalize(value(row,'description')) for row in fields.get('line_items',[]) if value(row,'description'))
        ia,ib=descriptions(a),descriptions(b)
        if ia and len(ia)==len(ib) and similar('|'.join(ia),'|'.join(ib))>=ITEM_SIMILARITY:
            return {'rule':'missing_reference_with_items', 'reasons':['An invoice number is missing.',
                'Same supplier, date, currency, total and similar item descriptions.']}
    return None


def match_po(fields, po):
    reference = value(fields,'po_number')
    if not reference:
        return {'status':'not_requested','po_number':None,'version_id':None,'issues':[], 'matches':[],
                'scope':'No PO reference supplied; no PO match was performed.'}
    result = {'status':'matched','po_number':reference,'version_id':po['id'] if po else None,'issues':[], 'matches':[],
              'scope':'Whole-order quantity/unit-price comparison; no receipt, partial-invoice or cumulative billing checks.'}
    def issue(code, field, message, **details):
        result['issues'].append({'code':code,'field':field,'message':message,**details})
    if po is None:
        issue('po_not_found','po_number','No imported purchase order matches this reference.')
    else:
        if normalize(value(fields,'supplier_name')) != normalize(po['supplier_name']):
            issue('po_supplier_mismatch','supplier_name','Supplier does not match the purchase order.',expected=po['supplier_name'],observed=value(fields,'supplier_name'))
        if value(fields,'currency') != po['currency']:
            issue('po_currency_mismatch','currency','Currency does not match the purchase order.',expected=po['currency'],observed=value(fields,'currency'))
        rows = fields.get('line_items',[])
        grouped = defaultdict(list)
        for index,row in enumerate(rows):
            sku,description = normalize(value(row,'sku')),normalize(value(row,'description'))
            candidates = [line for line in po['lines'] if normalize(line['sku'])==sku] if sku else [
                line for line in po['lines'] if description and normalize(line['description'])==description]
            prefix=f'line_items[{index}]'
            if len(candidates)!=1:
                issue('po_item_ambiguous' if candidates else 'po_item_not_found',prefix,
                      'Item match is ambiguous.' if candidates else 'No PO line matches this item by SKU or exact normalized description.')
                continue
            line=candidates[0]; grouped[line['line_number']].append((index,row))
            result['matches'].append({'invoice_line_index':index,'po_line_number':line['line_number'],
                'method':'sku' if sku else 'normalized_description','expected_unit_price':line['unit_price'],
                'observed_unit_price':value(row,'unit_price')})
            price=number(value(row,'unit_price'))
            if price is None or abs(price-Decimal(line['unit_price']))>Decimal('.000001'):
                issue('po_price_mismatch',prefix+'.unit_price','Unit price differs from the PO (tolerance 0.000001).',
                      expected=line['unit_price'],observed=value(row,'unit_price'))
        for line in po['lines']:
            matched=grouped[line['line_number']]
            if not matched:
                issue('po_line_missing','po.lines['+line['line_number']+']','This PO line has no matched invoice item.')
                continue
            quantities=[number(value(row,'quantity')) for _,row in matched]
            quantity=sum(quantities,Decimal(0)) if all(q is not None for q in quantities) else None
            if quantity is None or abs(quantity-Decimal(line['quantity']))>Decimal('.000001'):
                issue('po_quantity_mismatch','po.lines['+line['line_number']+'].quantity',
                      'Combined invoice quantity differs from the ordered quantity (tolerance 0.000001).',
                      expected=line['quantity'],observed=str(quantity) if quantity is not None else None)
        if not rows:
            issue('po_no_invoice_items','line_items','Invoice has no items to match.')
    if result['issues']:
        result['status']='discrepancy'
    return result
