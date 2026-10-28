export interface Evidence { page:number; bbox:[number,number,number,number]; text:string; method:string; span_ids:string[] }
export interface ExtractedField { value:string|number|null; status:'observed'|'proposed'|'missing'|'ambiguous'|'corrected'; reason:string|null; evidence:Evidence[] }
export interface Extraction { [key:string]:ExtractedField|Record<string,ExtractedField>[]|string|string[]; line_items:Record<string,ExtractedField>[]; taxes:Record<string,ExtractedField>[] }
export interface Issue { code:string; message:string; field?:string; severity?:string }
export interface ApiMatching { allowed:boolean; token:string; blockers:Issue[]; requires_po_exception:boolean; coverage_notice:string; duplicates:{document_id:string;filename:string;decision:string;reasons:string[]}[]; purchase_order:{status:string;po_number?:string;issues:Issue[]} }
export interface ApiReview { document_id:string; revision:number; current_revision:number; status:string; fields:Extraction; source_run_id:string; newer_candidate_available:boolean; validation:{issues:Issue[];assumptions:{field:string;value:unknown;reason:string}[]}; confirmation:{allowed:boolean;blockers:Issue[];warning_count:number}; matching:ApiMatching; pages:{page:number;method:string;image_url:string}[] }
export interface ApiHistory { revisions:{revision:number;created_at:number;actor:string;reason:string;action:string;changes:unknown[]}[] }
export interface ApiSession { user:string|null; role:string; authenticated:boolean }
export interface ApiDocument { id:string; filename:string; media_type:string; status:string; page_count:number|null; created_at:string; job:{status:string;error:string|null}|null; extraction:{run_id?:string|null;status?:string;job?:{status:string;error?:string|null}}; review:{status:string;revision:number|null}|null; source_url?:string; result?:{pages:{page:number;image_url:string}[]}|null }
export interface ReviewAction {expected_revision:number;actor:string;reason:string}
export interface ReviewUpdate extends ReviewAction { fields:Record<string,string|null>;verified_fields:string[]; line_items?:({source_index:number}&Record<string,string|number|null>)[];taxes?:({source_index:number}&Record<string,string|number|null>)[] }
export interface ReviewDecision extends ReviewAction {decision:'approved'|'rejected';acknowledge_warnings:boolean;matching_token:string;acknowledge_po_exception:boolean}
