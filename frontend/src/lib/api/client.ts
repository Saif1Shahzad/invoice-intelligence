import type { ApiDocument, ApiHistory, ApiMatching, ApiReview, ApiSession, ReviewUpdate, ReviewDecision } from './types';
export const LOCAL_HOST_RE = /^(https?:\/\/)?(localhost|127\.|0\.0\.0\.0|\[::1\])/i;
export function validateBase(base:string,_pageHost:string):string|null {
  return !base.trim() || base.trim()==='/' ? null : 'Use / for the configured secure connection. The server destination is set during deployment.';
}
export class ApiError extends Error { constructor(public status:number,message:string) {super(message)} }
export function createClient(base:string) {
  if(base!=='/')throw new Error('Only same-origin API connections are supported.');
  const req=async <T>(path:string,init?:RequestInit):Promise<T>=>{
    const res=await fetch(path,{...init,credentials:'same-origin',signal:AbortSignal.timeout(path.endsWith('/process')?240000:45000),headers:{Accept:'application/json',...init?.headers}});
    if(!res.ok){let msg=res.statusText;try{const j=await res.json();msg=j.error?.message??(typeof j.detail==='string'?j.detail:JSON.stringify(j.detail??j))}catch{}throw new ApiError(res.status,msg)}
    if(!res.headers.get('content-type')?.includes('application/json'))throw new ApiError(502,'The invoice backend is not configured at this address.');
    return res.json() as Promise<T>;
  };
  const doc=(id:string)=>`/v1/documents/${encodeURIComponent(id)}`;
  return {
    health:async()=>{const h=await req<{status:string;version:string}>('/health');if(h.status!=='ok'||!h.version)throw new Error('This is not an invoice backend.');return h},
    session:()=>req<ApiSession>('/v1/session'),
    listDocuments:async(limit=50,offset=0)=>{const r=await req<{documents:ApiDocument[]}>(`/v1/documents?limit=${limit}&offset=${offset}`);if(!Array.isArray(r.documents))throw new Error('Unexpected document response.');return r.documents},
    uploadDocument:async(file:File)=>{const fd=new FormData();fd.append('file',file);return req<ApiDocument>('/v1/documents',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:fd})},
    processDocument:(id:string)=>req<{document:ApiDocument}>(doc(id)+'/process',{method:'POST'}),
    getDocument:(id:string)=>req<ApiDocument>(doc(id)),getReview:(id:string)=>req<ApiReview>(doc(id)+'/review'),getHistory:(id:string)=>req<ApiHistory>(doc(id)+'/review/history'),getMatching:(id:string)=>req<ApiMatching>(doc(id)+'/matching'),
    saveReview:(id:string,body:ReviewUpdate)=>req<ApiReview>(doc(id)+'/review',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
    decideReview:(id:string,body:ReviewDecision)=>req<ApiReview>(doc(id)+'/review/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
    exportUrl:(fmt:'csv'|'json'|'xlsx')=>`/v1/exports/confirmed.${fmt}`,
  };
}
export type ApiClient=ReturnType<typeof createClient>;
