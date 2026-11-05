import {icon,readLocal} from '/assets/ui/app.js';
const $=id=>document.getElementById(id);
const examples={
 '2d':{title:'Neuron · 2D',route:'/demo',base:'/assets/demo/'},
 '3d':{title:'Neuron · 3D',route:'/demo/3d',base:'/assets/demo3d/'},
 'attention2d':{title:'Transformer · 2D',route:'/demo/attention/2d',base:'/assets/attention2d/'},
 'attention3d':{title:'Transformer · 3D',route:'/demo/attention/3d',base:'/assets/attention3d/'}
};
const params=new URLSearchParams(location.search);
// ?example= wins; otherwise the example of the last opened lesson; otherwise 2D.
const lastExample=Object.keys(examples).find(key=>examples[key].route===readLocal('ptw-last-visit')?.path);
const selected=examples[params.get('example')]?params.get('example'):lastExample||'2d';
let mode='examples',source='pdf',file=null,uploading=false;
// Switching examples reloads Home, so the previous world module and its animation loop are gone completely.
function selectExample(value){if(value===selected)return;const url=new URL(location.href);url.searchParams.set('example',value);location.replace(url);}
function showSelectedExample(){
 const item=examples[selected];
 document.querySelectorAll('[data-example]').forEach(button=>{const active=button.dataset.example===selected;button.setAttribute('aria-checked',String(active));button.tabIndex=active?0:-1;button.classList.toggle('selected',active);});
 if(params.has('example'))document.querySelector(`[data-example="${selected}"]`).focus();
 $('preview-title').textContent=item.title;$('open-example').href=item.route;$('preview-open').href=item.route;
}
// The preview is the example's lesson 1, drawn by the same world module the lesson uses.
async function loadPreview(){
 const item=examples[selected];
 try{
  const response=await fetch(item.base+'lessons.json');if(!response.ok)throw new Error();
  const lesson=(await response.json())[0];const world=await import(item.base+'world.js');
  const container=$('world');await world.init(container);world.setLesson(lesson.scene_state);world.onObjectClick(id=>world.highlight(id));world.play();
  $('world-dimension').textContent=`${world.dimensionality}D world`;$('caption').textContent=`Fig. 1 — ${lesson.figure_caption}`;
  window.addEventListener('app-themechange',event=>container.dispatchEvent(new CustomEvent('themechange',{detail:event.detail})));
  $('preview-sliders').replaceChildren(...lesson.controls.map(control=>{
   const row=document.createElement('div');row.className='preview-slider';
   const binary=control.min===0&&control.max===1&&control.step===1;
   if(binary){const options=control.symbol==='source'?['I see cats','I like cats']:['Off','On'];row.innerHTML=`<label for="preview-${control.symbol}">${control.label}<output hidden></output></label><select id="preview-${control.symbol}">${options.map((label,i)=>`<option value="${i}" ${i===control.default?'selected':''}>${label}</option>`).join('')}</select>`;}
   else row.innerHTML=`<label for="preview-${control.symbol}">${control.label}<output>${control.default} ${control.units}</output></label><input id="preview-${control.symbol}" type="range" min="${control.min}" max="${control.max}" step="${control.step}" value="${control.default}">`;
   row.querySelector('input,select').oninput=event=>{row.querySelector('output').textContent=`${event.target.value} ${control.units}`;world.setParams({[control.symbol]:Number(event.target.value)});};
   return row;}));
  let playing=true;const play=$('preview-play');play.disabled=false;
  play.onclick=()=>{playing=!playing;playing?world.play():world.pause();play.innerHTML=icon(playing?'pause':'play');play.setAttribute('aria-label',playing?'Pause preview':'Play preview');$('clock-status').textContent=playing?'Running':'Paused';};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)world.pause();else if(playing)world.play();});
 }catch{$('preview-error').hidden=false;$('preview-error').textContent='This preview couldn’t load. Open the example to try again. 3D requires browser graphics support.';}
}
function selectMode(value,focus=false){
 mode=value;for(const name of ['examples','paper']){const active=name===value;$(name+'-tab').setAttribute('aria-selected',String(active));$(name+'-tab').tabIndex=active?0:-1;$(name+'-panel').hidden=!active;if(active&&focus)$(name+'-tab').focus();}
 const url=new URL(location.href);url.searchParams.set('mode',value);history.replaceState({},'',url);
}
function selectSource(value,focus=false){source=value;for(const name of ['pdf','arxiv']){const active=value===name;$(name+'-tab').setAttribute('aria-selected',String(active));$(name+'-tab').tabIndex=active?0:-1;$(name+'-source').hidden=!active;if(active&&focus)$(name+'-tab').focus();}showError('status','');}
function arrowTabs(element,items,select){element.addEventListener('keydown',event=>{if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;event.preventDefault();const buttons=[...element.querySelectorAll('[role=tab],[role=radio]')];let index=buttons.indexOf(document.activeElement);index=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowRight'?1:-1)+items.length)%items.length;select(items[index],true);});}
$('examples-tab').onclick=()=>selectMode('examples');$('paper-tab').onclick=()=>selectMode('paper');
$('pdf-tab').onclick=()=>selectSource('pdf');$('arxiv-tab').onclick=()=>selectSource('arxiv');
arrowTabs(document.querySelector('.mode-tabs'),['examples','paper'],selectMode);arrowTabs(document.querySelector('.source-tabs'),['pdf','arxiv'],selectSource);arrowTabs(document.querySelector('.example-options'),Object.keys(examples),selectExample);
document.querySelectorAll('[data-example]').forEach(button=>button.onclick=()=>selectExample(button.dataset.example));
showSelectedExample();loadPreview();
function showError(id,message){$(id).textContent=message;$(id).hidden=!message;}
function setFile(next){
 if(next&&!/\.pdf$/i.test(next.name)&&next.type!=='application/pdf'){showError('status','Choose a PDF file to continue.');return;}
 file=next;showError('status','');$('drop-zone').classList.toggle('has-file',!!file);$('file-title').textContent=file?file.name:'Drop your paper here';$('file-detail').textContent=file?`${(file.size/1024/1024).toFixed(2)} MB · PDF selected`:'or choose a PDF from your computer';document.querySelector('.choose-file').textContent=file?'Choose a different PDF':'Choose PDF';$('remove-file').hidden=!file;
}
$('pdf').onchange=()=>setFile($('pdf').files[0]||null);$('remove-file').onclick=()=>{$('pdf').value='';setFile(null);$('pdf').focus();};
for(const event of ['dragenter','dragover'])$('drop-zone').addEventListener(event,e=>{e.preventDefault();$('drop-zone').classList.add('dragging');});
for(const event of ['dragleave','drop'])$('drop-zone').addEventListener(event,e=>{e.preventDefault();$('drop-zone').classList.remove('dragging');if(event==='drop')setFile(e.dataTransfer.files[0]||null);});
async function post(data){const response=await fetch('/api/runs',{method:'POST',body:data});const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'We couldn’t start this world. Please try again.');location.assign(`/build/${encodeURIComponent(result.id)}`);}
$('upload').onsubmit=async event=>{
 event.preventDefault();if(uploading)return;const data=new FormData();
 if(source==='pdf'){if(!file){showError('status','Choose a PDF first, or switch to arXiv paper.');$('pdf').focus();return;}data.append('file',file);}
 else{const id=$('arxiv').value.trim().replace(/^https?:\/\/(?:www\.)?arxiv\.org\/(?:abs|pdf)\//i,'').replace(/\.pdf$/i,'');if(!id){showError('status','Enter an arXiv ID or link first.');$('arxiv').focus();return;}data.append('arxiv_id',id);}
 uploading=true;const button=$('build-paper');const previous=button.innerHTML;button.disabled=true;button.textContent=source==='pdf'?'Uploading your paper…':'Opening your paper…';showError('status','');
 try{await post(data);}catch(error){showError('status',error.message);button.innerHTML=previous;button.disabled=false;uploading=false;}
};
async function availability(){try{const response=await fetch('/api/config');if(!response.ok)throw new Error();const config=await response.json();$('availability').classList.toggle('connected',config.generation_available);$('availability').textContent=config.generation_available?'Upload a paper to start building your world.':config.problem;$('build-paper').disabled=!config.generation_available;}catch{$('availability').textContent='We couldn’t check availability. You can still try submitting your paper.';}}
const visit=readLocal('ptw-last-visit');if(visit?.lesson&&/^\/(?:demo(?:\/3d|\/attention\/[23]d)?|learn\/[\w-]+)$/.test(visit.path)){$('resume').href=visit.path;const example=Object.values(examples).find(item=>item.route===visit.path);$('resume-title').textContent=`${example?example.title:visit.world} · Lesson ${visit.lesson} of ${visit.total}: ${visit.title}`;$('resume').hidden=false;}
selectMode(new URLSearchParams(location.search).get('mode')==='paper'?'paper':'examples');
availability();
