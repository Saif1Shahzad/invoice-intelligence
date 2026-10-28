import type { ApiReview } from './api/types';
export function canApproveLive(r:ApiReview,state:{dirty:boolean;busy:boolean;conflict:boolean;writable:boolean;reason:string;actor:string;ackWarnings:boolean;ackPO:boolean}):boolean {
  return state.writable&&!state.busy&&!state.dirty&&!state.conflict&&!r.newer_candidate_available&&r.revision===r.current_revision&&r.status==='pending'&&r.confirmation.allowed&&r.matching.allowed&&(!r.confirmation.warning_count||state.ackWarnings)&&(!r.matching.requires_po_exception||state.ackPO)&&!!state.reason.trim()&&!!state.actor.trim();
}
