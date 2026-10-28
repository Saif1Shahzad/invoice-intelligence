import { describe, it, expect, vi, afterEach } from 'vitest';
import { canApproveLive } from '../lib/live-policy';
import { makeSampleDocs } from '../lib/sample-data';
import { blockers, canConfirm, canReject } from '../lib/review';
import { createClient, ApiError, validateBase } from '../lib/api/client';
import type { ApiReview } from '../lib/api/types';
const review={revision:2,current_revision:2,status:'pending',newer_candidate_available:false,confirmation:{allowed:true,warning_count:0},matching:{allowed:true,requires_po_exception:false}} as ApiReview;
const ready={dirty:false,busy:false,conflict:false,writable:true,reason:'Checked source',actor:'Reviewer',ackWarnings:false,ackPO:false};
afterEach(()=>vi.unstubAllGlobals());
describe('Human review decisions',()=>{
 it('allows a clean, validated review only',()=>expect(canApproveLive(review,ready)).toBe(true));
 for(const key of ['dirty','busy','conflict'] as const)it(`blocks ${key}`,()=>expect(canApproveLive(review,{...ready,[key]:true})).toBe(false));
 it('blocks viewers and missing identity/reason',()=>{expect(canApproveLive(review,{...ready,writable:false})).toBe(false);expect(canApproveLive(review,{...ready,reason:' '})).toBe(false);expect(canApproveLive(review,{...ready,actor:''})).toBe(false)});
 it('blocks validation and duplicate holds',()=>{expect(canApproveLive({...review,confirmation:{...review.confirmation,allowed:false}},ready)).toBe(false);expect(canApproveLive({...review,matching:{...review.matching,allowed:false}},ready)).toBe(false)});
 it('requires explicit warning and PO acknowledgement',()=>{const r={...review,confirmation:{...review.confirmation,warning_count:1},matching:{...review.matching,requires_po_exception:true}};expect(canApproveLive(r,ready)).toBe(false);expect(canApproveLive(r,{...ready,ackWarnings:true,ackPO:true})).toBe(true)});
 it('blocks stale candidates and decided invoices',()=>{expect(canApproveLive({...review,newer_candidate_available:true},ready)).toBe(false);expect(canApproveLive({...review,current_revision:3},ready)).toBe(false);expect(canApproveLive({...review,status:'approved'},ready)).toBe(false)});
 it('keeps sample holds and reason rules active',()=>{const d=makeSampleDocs().find(d=>d.status==='needs_review')!;expect(blockers(d).length).toBeGreaterThan(0);expect(canConfirm(d)).toBe(false);expect(canReject(d,' ')).toBe(false);expect(canReject(d,'Wrong supplier')).toBe(true)});
});
describe('Backend adapter',()=>{
 it('refuses arbitrary backend destinations',()=>{expect(validateBase('https://example.com','site.vercel.app')).toBeTruthy();expect(validateBase('/','site.vercel.app')).toBeNull();expect(()=>createClient('https://example.com')).toThrow()});
 it('does not interpret SPA HTML as a working backend',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html/>',{headers:{'Content-Type':'text/html'}})));await expect(createClient('/').health()).rejects.toBeInstanceOf(ApiError)});
 it('uses PATCH with explicit verification and revision',async()=>{const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(review),{headers:{'Content-Type':'application/json'}}));vi.stubGlobal('fetch',fetch);await createClient('/').saveReview('invoice/1',{expected_revision:2,actor:'Reviewer',reason:'Verified',fields:{supplier_name:'Supplier'},verified_fields:['supplier_name']});expect(fetch.mock.calls[0]?.[0]).toBe('/v1/documents/invoice%2F1/review');expect(fetch.mock.calls[0]?.[1].method).toBe('PATCH');expect(JSON.parse(fetch.mock.calls[0]?.[1].body).verified_fields).toEqual(['supplier_name'])});
 it('surfaces revision conflicts without retrying',async()=>{const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({error:{message:'Revision changed'}}),{status:409,headers:{'Content-Type':'application/json'}}));vi.stubGlobal('fetch',fetch);await expect(createClient('/').getReview('a')).rejects.toMatchObject({status:409});expect(fetch).toHaveBeenCalledTimes(1)});
});
