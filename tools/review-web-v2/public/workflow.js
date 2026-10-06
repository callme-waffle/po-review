'use strict';
let workflowStates={},workflowBusy=false,workflowPolling=false,uploadTicket=null;
const approvalLabel=s=>s?.approval==='approved'?'승인 완료':s?.approval==='stale'?'재승인 필요':'미승인';
const remoteLabel=s=>({synced:'원격 반영됨',pending:'업로드 대기',unknown:'원격 미확인',error:'원격 확인 실패'}[s?.remote]||'원격 미확인');
function statusText(id){const s=workflowStates[id];return `${approvalLabel(s)} · ${remoteLabel(s)}`;}
async function postWorkflow(path,data={}){return request(path,{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify(data)});}
function renderWorkflow(){
 const s=workflowStates[current?.id];$('approval-state').textContent=approvalLabel(s);$('remote-state').textContent=remoteLabel(s);
 $('remote-state').title=s?.remote_error|| (s?.checked_at?'마지막 확인: '+new Date(s.checked_at).toLocaleString():'');
 $('approve-document').textContent=s?.approved?'승인 취소':'현재 문서 승인';$('approve-document').disabled=!s||workflowBusy||dirty();
 const pending=Object.values(workflowStates).filter(s=>s.remote==='pending').length;
 $('upload-open').textContent=`업로드 (${pending})`;$('upload-open').disabled=workflowBusy;
 $('remote-refresh').disabled=workflowBusy;
}
async function refreshWorkflow(){if(workflowPolling)return;workflowPolling=true;try{const r=await request('/api/workflow');workflowStates=Object.fromEntries(r.documents.map(s=>[s.id,s]));workflowBusy=r.busy;renderWorkflow();drawDocs();const job=r.job;$('workflow-message').textContent=!job?'':job.state==='running'?(job.kind==='upload'?'업로드 및 반영 확인 중…':'원격 상태 확인 중…'):job.state==='failed'?job.error:job.kind==='upload'?(job.result||[]).map(x=>`${x.component}: ${x.message}`).join(' / '):`원격 확인 완료 · 실패 ${(job.result||[]).filter(x=>!x.ok).length}개 구성요소`;}catch(e){error(e.message);}finally{workflowPolling=false;}}
$('approve-document').addEventListener('click',async()=>{try{if(dirty())throw Error('편집 내용을 먼저 저장해 주세요.');const s=workflowStates[current.id];await postWorkflow('/api/approve',{documents:[{id:current.id,revision:s.revision}],approved:!s.approved});await refreshWorkflow();}catch(e){error(e.message);}});
$('remote-refresh').addEventListener('click',async()=>{try{await postWorkflow('/api/remote-refresh');await refreshWorkflow();}catch(e){error(e.message);}});
function queueItems(){return [...$('upload-list').querySelectorAll('input:checked')].map(n=>({id:n.value,revision:n.dataset.revision}));}
function invalidatePreview(){uploadTicket=null;$('upload-confirm').disabled=true;$('upload-preview-message').textContent='선택한 문서의 업로드 내용을 확인해 주세요.';}
$('upload-open').addEventListener('click',async()=>{
 if(dirty()){error('편집 내용을 먼저 저장해 주세요.');return;}
 await refreshWorkflow();$('upload-list').replaceChildren();invalidatePreview();
 for(const d of docs){const s=workflowStates[d.id];if(s?.remote!=='pending')continue;const row=el('label','upload-row'),box=el('input');box.type='checkbox';box.value=d.id;box.dataset.revision=s.revision;row.append(box,el('span','',`${d.project} / ${d.source} — ${approvalLabel(s)}`));box.addEventListener('change',invalidatePreview);$('upload-list').append(row);}
 if(!$('upload-list').children.length)$('upload-list').append(el('p','','업로드 대기 문서가 없습니다. 원격 미확인·실패 문서는 원격 상태 확인을 먼저 진행해 주세요.'));
 $('upload-dialog').showModal();
});
$('upload-close').addEventListener('click',()=>$('upload-dialog').close());
$('upload-select-approved').addEventListener('click',()=>{for(const n of $('upload-list').querySelectorAll('input'))n.checked=workflowStates[n.value]?.approved;invalidatePreview();});
$('upload-approve').addEventListener('click',async()=>{try{const items=queueItems();if(!items.length)throw Error('문서를 선택해 주세요.');await postWorkflow('/api/approve',{documents:items,approved:true});await refreshWorkflow();$('upload-preview-message').textContent='선택한 문서를 승인했습니다. 업로드 내용 확인을 눌러 주세요.';for(const n of $('upload-list').querySelectorAll('input')){const d=docs.find(d=>d.id===n.value);n.nextSibling.textContent=`${d.project} / ${d.source} — ${approvalLabel(workflowStates[n.value])}`;}}catch(e){$('upload-preview-message').textContent=e.message;}});
$('upload-preview').addEventListener('click',async()=>{try{invalidatePreview();const p=await postWorkflow('/api/upload-preview',{documents:queueItems()});uploadTicket=p.ticket;$('upload-preview-message').textContent=`${p.components}개 구성요소의 ${p.entries}개 번역 항목을 전송합니다. 공유 항목을 포함해 영향받는 문서 ${p.documents.length}개:\n`+p.documents.map(d=>`${d.project} / ${d.source}`).join('\n')+'\n원격에서 승인된 번역은 덮어쓰지 않습니다. 미반영 항목은 대기 상태로 남습니다.';$('upload-confirm').disabled=false;}catch(e){$('upload-preview-message').textContent=e.message;}});
$('upload-confirm').addEventListener('click',async()=>{if(!uploadTicket)return;const ticket=uploadTicket;invalidatePreview();try{await postWorkflow('/api/upload',{ticket});$('upload-dialog').close();await refreshWorkflow();}catch(e){$('upload-preview-message').textContent=e.message;}});
setInterval(()=>{if(token&&!document.hidden)refreshWorkflow();},5000);
