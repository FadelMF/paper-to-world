import {icon} from '/assets/ui/app.js';
const $ = id => document.getElementById(id);
const runId = location.pathname.split('/').pop();
const api = `/api/runs/${encodeURIComponent(runId)}`;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
let lastStep = 1, busy = false, stopped = false, redirectTimer, ready = false;
let hints = [], hintIndex = 0, hintKey = '';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function setText(id, text) { if ($(id).textContent !== text) $(id).textContent = text; }
async function request(url, method = 'GET') {
  const response = await fetch(url, {method});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'We couldn’t open this paper.');
  return data;
}
function circles(steps) {
  [...$('steps').children].forEach((li, i) => {
    if (li.dataset.state !== steps[i].state) li.dataset.state = steps[i].state;
    li.setAttribute('aria-label', `${steps[i].label}: ${steps[i].state === 'error' ? 'stopped' : steps[i].state}`);
    if (steps[i].state === 'active') li.setAttribute('aria-current', 'step');
    else li.removeAttribute('aria-current');
  });
  const current=steps.findIndex(step=>step.state==='active'||step.state==='error');
  const detail=document.querySelector('.card-body');
  const parent=current<0?document.querySelector('.build-card'):$('steps').children[current];
  if(detail.parentElement!==parent)parent.append(detail);
}
function renderActivity(items) {
  const existing = new Map([...$('activity').children].map(el => [el.dataset.key, el]));
  items.forEach((item, index) => {
    let li = existing.get(item.key);
    if (!li) {
      li = document.createElement('li'); li.dataset.key = item.key; li.className = 'new';
      const mark = document.createElement('span'); mark.className = 'activity-mark'; mark.setAttribute('aria-hidden','true');
      const text = document.createElement('span'); text.textContent = item.text;
      li.append(mark, text);
    }
    li.dataset.done = String(item.done);
    li.lastChild.textContent = item.text;
    li.lastChild.title = item.text;
    li.firstChild.textContent = item.done ? '✓' : '•';
    if ($('activity').children[index] !== li) $('activity').insertBefore(li, $('activity').children[index] || null);
    existing.delete(item.key);
  });
  existing.forEach(el => el.remove());
}
function renderDiscoveries(d) {
  $('discovery-empty').hidden = !!(d.title || d.concepts.length || d.equations.length || d.modality || d.checks);
  setText('paper-title', d.title); $('paper-title').hidden = !d.title;
  setText('authors', d.authors); $('authors').hidden = !d.authors;
  const chips = new Set([...$('concepts').children].map(el => el.textContent));
  let added = 0;
  d.concepts.forEach(name => { if (!chips.has(name)) { const chip=document.createElement('span'); chip.className='chip'; chip.textContent=name; chip.style.animationDelay=`${added++ * 120}ms`; $('concepts').append(chip); chips.add(name); } });
  const equations = new Set([...$('equations').children].map(el => el.dataset.latex));
  d.equations.slice(0,2).forEach(eq => {
    if (equations.has(eq.latex)) return;
    const row=document.createElement('div'); row.className='equation'; row.dataset.latex=eq.latex;
    const math=document.createElement('div'); math.className='math';
    if (window.katex) window.katex.render(eq.latex,math,{throwOnError:false,trust:false}); else math.textContent=eq.latex;
    const meaning=document.createElement('p'); meaning.className='meaning'; meaning.textContent=eq.meaning;
    row.append(math,meaning); $('equations').append(row);
  });
  const validView = d.modality === '2d' || d.modality === '3d';
  $('view-choice').hidden = !validView;
  if (validView) { setText('modality',d.modality.toUpperCase()); if($('view-icon').dataset.mode!==d.modality){$('view-icon').innerHTML=icon(d.modality==='3d'?'cube':'chart');$('view-icon').dataset.mode=d.modality;} setText('modality-reason',d.modality_reason); }
  $('checks').hidden = !d.checks;
  if (d.checks) { setText('checks',`${d.checks.passed} of ${d.checks.total} results match the paper`); $('checks').dataset.allPass=String(d.checks.total>0 && d.checks.passed===d.checks.total); }
}
function enter() { if (ready && !stopped) { stopped=true; clearTimeout(redirectTimer); location.assign(`/learn/${encodeURIComponent(runId)}`); } }
async function render(data) {
  const s=data.status;
  $('sample-note').hidden=!data.demo;
  // Animate already-completed transitions even if a quick stage fell between polls.
  for (let step=lastStep+1; step<s.step; step++) {
    if (stopped) return;
    circles(s.steps.map((item,i)=>({...item,state:i<step-1?'done':i===step-1?'active':'pending'})));
    setText('mobile-step',s.steps[step-1].label);
    if (!reduced) await delay(400);
  }
  if (stopped) return;
  lastStep=s.step; circles(s.steps); setText('mobile-step',s.steps[s.step-1].label);
  setText('headline',s.headline); setText('subline',s.subline);
  renderActivity(s.activity); renderDiscoveries(s.discovered);
  const nextHints=JSON.stringify(s.waiting_hints);
  if (nextHints!==hintKey) { hintKey=nextHints; hints=s.waiting_hints; hintIndex=0; setText('waiting',hints[0] || ''); }
  if (s.done) { hints=[]; setText('waiting','');  }
  $('retry').hidden=!s.error;
  if (s.error) { clearTimeout(redirectTimer); $('enter').hidden=true; setText('cancel','Back to papers'); }
  if (!ready && s.done && !s.error && s.step===5 && data.has_world) {
    ready=true; $('enter').disabled=false; $('enter').classList.add('ready');
    redirectTimer=setTimeout(enter,2000);
  }
}
async function poll() {
  if (busy || stopped || ready) return;
  busy=true;
  try { const data=await request(api); $('connection').hidden=true; await render(data); }
  catch { setText('connection','We couldn’t check the latest progress. We’ll keep trying; your work may still be continuing.'); $('connection').hidden=false; }
  finally { busy=false; }
}
$('enter').onclick=enter;
$('cancel').onclick=async()=>{
  stopped=true; clearTimeout(redirectTimer); $('cancel').disabled=true;
  try { await request(`${api}/cancel`,'POST'); location.assign('/'); }
  catch { stopped=false; $('cancel').disabled=false; setText('connection','We couldn’t stop this world yet. Please try Cancel again.'); $('connection').hidden=false; }
};
$('retry').onclick=async()=>{
  $('retry').disabled=true;
  try { const result=await request(`${api}/retry`,'POST'); stopped=true; location.assign(`/build/${encodeURIComponent(result.id)}`); }
  catch(error) { setText('connection',error.message); $('connection').hidden=false; $('retry').disabled=false; }
};
const polling=setInterval(poll,1500);
const waiting=setInterval(()=>{if(!hints.length || stopped || ready)return;hintIndex=(hintIndex+1)%hints.length;setText('waiting',hints[hintIndex]);$('waiting').classList.remove('changed');void $('waiting').offsetWidth;$('waiting').classList.add('changed');},4000);
window.addEventListener('pagehide',()=>{stopped=true;clearInterval(polling);clearInterval(waiting);clearTimeout(redirectTimer);});
poll();
