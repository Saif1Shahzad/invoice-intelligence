import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { useApp } from '@/lib/app-state';
import { ApiError } from '@/lib/api/client';
import type { ApiReview, ApiHistory, ApiSession, ExtractedField, Evidence, ReviewUpdate } from '@/lib/api/types';
import { Panel, BackendNotConnected, StatusBadge } from './bits';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { ZoomBar } from './source-view';
import { canApproveLive } from '@/lib/live-policy';

const label=(key:string)=>key.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
const isField=(v:unknown):v is ExtractedField=>!!v&&typeof v==='object'&&'status' in v&&'value' in v;
export function LiveReview({id}:{id:string}) {
  const {client,conn,refreshLive}=useApp();
  const [review,setReview]=useState<ApiReview|null>(null),[history,setHistory]=useState<ApiHistory|null>(null),[session,setSession]=useState<ApiSession|null>(null);
  const [draft,setDraft]=useState<Record<string,string>>({}),[verified,setVerified]=useState<string[]>([]),[reason,setReason]=useState(''),[actor,setActor]=useState('');
  const [err,setErr]=useState(''),[busy,setBusy]=useState(false),[conflict,setConflict]=useState(false),[notice,setNotice]=useState('');
  const [active,setActive]=useState<Evidence|null>(null),[page,setPage]=useState(1),[zoom,setZoom]=useState(1),[tab,setTab]=useState('Fields');
  const [ack,setAck]=useState(false),[poAck,setPoAck]=useState(false);
  const dirty=Object.keys(draft).length>0||verified.length>0;
  const accept=(r:ApiReview)=>{setReview(r);setDraft({});setVerified([]);setConflict(false);setReason('');setAck(false);setPoAck(false);setNotice('Saved. Review history is persistent.');refreshLive()};
  useEffect(()=>{if(!client||conn!=='reachable')return;let off=false;setReview(null);setErr('');setDraft({});setVerified([]);setConflict(false);Promise.all([client.getReview(id),client.getHistory(id),client.session()]).then(([r,h,s])=>{if(!off){setReview(r);setHistory(h);setSession(s);setPage(r.pages[0]?.page??1)}}).catch(e=>!off&&setErr(e.message));return()=>{off=true}},[id,client,conn]);
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty]);
  if(conn!=='reachable'||!client)return <BackendNotConnected what="Invoice review"/>;
  if(!review)return <Panel className="p-6">{err||'Loading invoice review…'}</Panel>;
  const writable=session?.role==='reviewer'||session?.role==='admin';
  const editable=writable&&!busy&&!conflict&&!review.newer_candidate_available;
  const approved=canApproveLive(review,{dirty,busy,conflict,writable,reason,actor:session?.user||actor,ackWarnings:ack,ackPO:poAck});
  const mutate=async(decision?:'approved'|'rejected')=>{
    const identity=session?.user||actor.trim();if(!reason.trim()||!identity){setErr('Enter your reviewer name and a reason.');return}
    setBusy(true);setErr('');setNotice('');
    try {
      const base={expected_revision:review.revision,actor:identity,reason:reason.trim()};let r:ApiReview;
      if(decision){r=await client.decideReview(id,{...base,decision,acknowledge_warnings:ack,acknowledge_po_exception:poAck,matching_token:review.matching.token})}
      else {
        const body:ReviewUpdate={...base,fields:{},verified_fields:verified};
        for(const [key,value] of Object.entries(draft))if(!key.includes('['))body.fields[key]=value;
        for(const collection of ['line_items','taxes'] as const){
          if(Object.keys(draft).some(k=>k.startsWith(collection+'[')))body[collection]=review.fields[collection].map((row,i)=>({source_index:i,...Object.fromEntries(Object.entries(row).map(([key,f])=>[key,draft[`${collection}[${i}].${key}`]??(f.value==null?null:String(f.value))]))}));
        }
        r=await client.saveReview(id,body);
      }
      accept(r);setHistory(await client.getHistory(id));
    }catch(e){if(e instanceof ApiError&&e.status===409)setConflict(true);setErr(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  };
  const field=(key:string,f:ExtractedField)=>{
    const value=draft[key]??(f.value==null?'':String(f.value));
    return <div key={key} className="rounded-md border border-border p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs"><strong>{label(key)}</strong><StatusBadge status={verified.includes(key)?'verified':f.status}/>{f.evidence.length>0&&<button className="ml-auto text-primary underline" onClick={()=>{const ev=f.evidence[0]!;setActive(ev);setPage(ev.page)}}>Show source</button>}</div>
      <Input aria-label={label(key)} value={value} disabled={!editable} onChange={e=>{setDraft(d=>({...d,[key]:e.target.value}));setVerified(v=>v.filter(k=>k!==key))}}/>
      {f.reason&&<p className="mt-1 text-xs text-muted-foreground">{f.reason.replaceAll('_',' ')}</p>}
      {f.status==='proposed'&&<Button size="sm" variant="outline" className="mt-2" disabled={!editable||verified.includes(key)} onClick={()=>{setVerified(v=>[...v,key]);if(f.evidence[0]){setActive(f.evidence[0]);setPage(f.evidence[0].page)}}}>{verified.includes(key)?'Verification selected — save to record':'I checked this value against the source'}</Button>}
    </div>
  };
  const source=review.pages.find(p=>p.page===page);
  return <div className="mx-auto max-w-[1500px]">
    <div className="mb-4 flex flex-wrap items-center gap-3"><Link to="/review" className="text-primary" onClick={e=>{if(dirty&&!window.confirm('Discard unsaved review edits?'))e.preventDefault()}}>← Review queue</Link><h1 className="text-2xl">Invoice review</h1><StatusBadge status={review.status}/><span className="text-xs">Revision {review.revision}</span></div>
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel className="flex h-[60vh] flex-col overflow-hidden lg:sticky lg:top-4 lg:h-[calc(100vh-7rem)]">
        <ZoomBar zoom={zoom} setZoom={setZoom} label="Original source"/>
        <select className="border-b border-border bg-card p-2 text-sm" aria-label="Source page" value={page} onChange={e=>setPage(+e.target.value)}>{review.pages.map(p=><option key={p.page} value={p.page}>Page {p.page}</option>)}</select>
        <div className="min-h-0 flex-1 overflow-auto bg-muted/50 p-4">{source&&<div className="relative mx-auto" style={{width:560*zoom}}><img className="w-full" src={source.image_url} alt={`Original invoice page ${page}`}/>{active?.page===page&&<div aria-label="Selected field source location" className="pointer-events-none absolute border-2 border-primary bg-primary/15" style={{left:`${active.bbox[0]*100}%`,top:`${active.bbox[1]*100}%`,width:`${(active.bbox[2]-active.bbox[0])*100}%`,height:`${(active.bbox[3]-active.bbox[1])*100}%`}}/>}</div>}</div>
        {active&&<p className="border-t p-2 text-xs">Source text: {active.text}</p>}
      </Panel>
      <div className="space-y-4"><Panel><div className="flex overflow-auto border-b border-border">{['Fields','Line items','Checks','History'].map(t=><button key={t} className={`px-4 py-3 text-sm ${t===tab?'border-b-2 border-primary':''}`} onClick={()=>setTab(t)}>{t}</button>)}</div><div className="space-y-3 p-4">
        {tab==='Fields'&&Object.entries(review.fields).filter(([,v])=>isField(v)).map(([key,v])=>field(key,v as ExtractedField))}
        {tab==='Line items'&&(['line_items','taxes'] as const).map(collection=><section key={collection}><h2 className="mb-2 text-lg">{label(collection)}</h2>{review.fields[collection].map((row,i)=><div key={i} className="mb-4 space-y-2 rounded-lg border p-2"><h3 className="text-sm">Row {i+1}</h3>{Object.entries(row).map(([key,f])=>field(`${collection}[${i}].${key}`,f))}</div>)}</section>)}
        {tab==='Checks'&&<><p className="text-sm">{review.matching.coverage_notice}</p>{[...review.validation.issues,...review.matching.blockers,...review.matching.purchase_order.issues].map((x,i)=><div key={i} className="rounded border p-3 text-sm"><strong>{x.field??x.code}</strong><p>{x.message}</p></div>)}{review.matching.duplicates.map(d=><div key={d.document_id} className="rounded border p-3 text-sm"><strong>Possible duplicate: {d.filename}</strong><p>{d.reasons.join(' · ')}</p><p>Decision: {d.decision}</p><p className="text-xs">Resolve duplicate decisions in Advanced review before confirming. <a href="/legacy-review" className="underline text-primary">Open advanced review</a></p></div>)}</>}
        {tab==='History'&&history?.revisions.map(h=><div key={h.revision} className="border-b pb-3 text-sm"><strong>Revision {h.revision} · {h.actor}</strong><p>{h.action}: {h.reason}</p><p className="text-xs text-muted-foreground">{new Date(h.created_at*1000).toLocaleString()}</p></div>)}
      </div></Panel>
      <Panel className="space-y-3 p-4">
        {!writable&&<p className="text-sm">This account can view documents. A reviewer account is required to save or confirm.</p>}
        {review.newer_candidate_available&&<p className="text-sm text-destructive">A newer extraction exists. Use the backend review workspace to rebase before editing.</p>}
        {conflict&&<div className="text-sm text-destructive">The saved invoice changed. Your draft is preserved. Copy any edits before reloading.<Button variant="outline" onClick={()=>{if(window.confirm('Discard draft and reload the current invoice?'))window.location.reload()}}>Reload current invoice</Button></div>}
        {!session?.user&&<Input aria-label="Reviewer name" placeholder="Reviewer name" value={actor} onChange={e=>setActor(e.target.value)}/>}
        <Textarea aria-label="Reason for review action" placeholder="Reason for this correction or decision" value={reason} onChange={e=>setReason(e.target.value)}/>
        {review.confirmation.warning_count>0&&<label className="flex gap-2 text-sm"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>I reviewed the remaining warnings.</label>}
        {review.matching.requires_po_exception&&<label className="flex gap-2 text-sm"><input type="checkbox" checked={poAck} onChange={e=>setPoAck(e.target.checked)}/>Accept the documented PO discrepancy with my reason.</label>}
        {err&&<p role="alert" className="text-sm text-destructive">{err}</p>}{notice&&<p role="status" className="text-sm text-success">{notice}</p>}
        <p className="text-xs text-muted-foreground">{dirty?'Unsaved changes. Save and revalidate before confirming.':review.confirmation.allowed&&review.matching.allowed?'Validation passed. Inspect the source before confirming.':'Confirmation is blocked. See Checks for details.'}</p>
        <div className="flex flex-wrap gap-2"><Button disabled={!editable||!dirty||!reason.trim()||!(session?.user||actor.trim())} onClick={()=>mutate()}>Save and revalidate</Button><Button disabled={!approved} onClick={()=>mutate('approved')}>Confirm</Button><Button variant="outline" disabled={!editable||dirty||!reason.trim()||!(session?.user||actor.trim())} onClick={()=>mutate('rejected')}>Reject</Button></div>
      </Panel></div>
    </div>
  </div>;
}
