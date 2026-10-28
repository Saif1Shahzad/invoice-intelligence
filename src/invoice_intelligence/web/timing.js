'use strict';
let timerSession=null,timerActive=0,timerPaused=false,timerLast=performance.now(),timerActivity=timerLast,timerVisible=!document.hidden,timerSending=false,timerPending=null,timerStarting=false;
function timerTick(){const now=performance.now();if(timerSession&&!timerPaused&&timerVisible)timerActive+=Math.max(0,Math.min(now,timerActivity+60000)-timerLast);timerLast=now;$('timer-seconds').textContent=Math.floor(timerActive/1000)+'s';}
function timerControls(){const ready=!!review&&!busy&&currentAccount?.role!=='viewer';$('timer-start').disabled=!ready||!!timerSession||timerStarting||review?.status!=='pending';$('actor').readOnly=!!timerSession||timerStarting||!!currentAccount?.authenticated;$('timer-pause').disabled=!timerSession||timerSending;$('timer-stop').disabled=!timerSession||timerSending;$('timer-kind').disabled=!!timerSession;}
async function flushTimer(ended=false){
  timerTick();if(!timerSession||timerSending)return false;
  timerSending=true;timerControls();
  if(!timerPending)timerPending={sequence:timerSession.last_sequence+1,active_ms:Math.floor(timerActive),ended};
  const session=timerSession;
  try{const saved=await api(`/v1/documents/${session.document_id}/review-sessions/${session.id}/events`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(timerPending),keepalive:true});
    const finished=timerPending.ended;timerSession=saved;timerPending=null;
    if(finished){timerSession=null;$('timer-status').textContent='Timing session saved. This is measured browser activity, not a verified accounting review-time experiment.';}
    else $('timer-status').textContent=timerPaused?'Paused; saved time is persistent.':'Running; saved every 10 seconds. Hidden/idle time is excluded.';
    return true;
  }catch(e){$('timer-status').textContent='Timing not saved: '+e.message+' Retry Finish timer; its event is replay-safe.';return false;}
  finally{timerSending=false;timerControls();}
}
async function finishTimer(){if(!timerSession)return true;if(timerSending){notice('Timing is being saved. Please try again in a moment.');return false;}if(timerPending&&!await flushTimer())return false;if(!timerSession)return true;return await flushTimer(true);}
$('timer-start').addEventListener('click',async()=>{if(timerStarting||timerSession)return;timerStarting=true;timerControls();try{const actor=$('actor').value.trim();if(!actor)throw Error('Enter your reviewer name below before starting the timer.');const session=await api(url('/review-sessions'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:crypto.randomUUID(),actor,kind:$('timer-kind').value})});timerSession=session;timerActive=0;timerPaused=false;timerLast=performance.now();timerActivity=timerLast;$('timer-pause').textContent='Pause';$('timer-status').textContent='Timer running. Pause for interruptions; 60-second inactivity and hidden tabs are excluded.';timerControls();}catch(e){notice(e.message,true);}finally{timerStarting=false;timerControls();}});
$('timer-pause').addEventListener('click',()=>{timerTick();timerPaused=!timerPaused;timerLast=performance.now();timerActivity=timerLast;$('timer-pause').textContent=timerPaused?'Resume':'Pause';flushTimer();});
$('timer-stop').addEventListener('click',finishTimer);
for(const event of ['pointerdown','keydown','scroll'])document.addEventListener(event,()=>{timerTick();timerActivity=performance.now();},{passive:true});
document.addEventListener('visibilitychange',()=>{timerTick();timerVisible=!document.hidden;timerLast=performance.now();if(timerVisible)timerActivity=timerLast;else flushTimer();});
window.addEventListener('pagehide',()=>flushTimer());
setInterval(()=>{timerTick();timerControls();},1000);setInterval(()=>{if(timerSession)flushTimer();},10000);
