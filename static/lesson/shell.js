import {icon,readLocal,writeLocal} from '/assets/ui/app.js';
import {isolatedWorld} from './isolated-world.js';
const $ = id => document.getElementById(id);
// Prepared example routes and their current artifact bundles.
const demos = {
  '/demo': { key: '2d', base: '/assets/demo/', title:'Neuron · 2D' },
  '/demo/3d': { key: '3d', base: '/assets/demo3d/', title: 'Neuron · 3D' },
  '/demo/attention/2d': {key:'attention2d',base:'/assets/attention2d/',title:'Transformer · 2D'},
  '/demo/attention/3d': {key:'attention3d',base:'/assets/attention3d/',title:'Transformer · 3D'},
};
let example = demos[location.pathname];
const demo = Boolean(example);
const demo3d = demo && (location.pathname === '/demo/3d' || location.pathname.endsWith('/3d'));
const runId = demo ? null : location.pathname.split('/').pop();
let base = demo ? example.base : `/api/runs/${encodeURIComponent(runId)}/files/`;
let lessons, world, scene = null, evidence = null, current = 0, playing = true, exploring = false, narrating = false;
let selectedObject = null, narrationGeneration = 0, toastTimer;
const progress = new Map();
const sessionKey = `ptw-session:${location.pathname}`;
function saveSession(){if(!lessons)return;writeLocal(sessionKey,{current,progress:[...progress]});writeLocal('ptw-last-visit',{path:location.pathname,world:example?.title||lessons[0].source.title,lesson:current+1,total:lessons.length,title:lessons[current].title});}
// Simulation results are ours, not the paper's: they never get a page number.
// Only paper statements carry a page number.
function citation(kind,page){return kind==='simulation'?'From our simulation':kind==='background'?'Background':`p.${escapeHTML(page)}`;}
const challengeFunctions = new Map();
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
function notify(text) { $('announcement').textContent = text; }
function toast(text) { $('toast').textContent=text; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,4500); }
function fatal(error) { document.body.classList.remove('world-starting'); $('loading').hidden=false; $('loading-message').textContent=`This lesson could not load: ${error.message}`; $('workspace').hidden=true; $('controlbar').hidden=true; }
async function json(url, options) { const response=await fetch(url,options);const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`Request failed (${response.status})`);return data; }
function renderMath(element) { element.querySelectorAll('[data-latex]').forEach(el => window.katex.render(el.dataset.latex,el,{displayMode:el.classList.contains('equation-math'),throwOnError:false,trust:false})); }
function stateFor(lesson) { if(!progress.has(lesson.id))progress.set(lesson.id,{prediction:null,revealed:false,achieved:false});return progress.get(lesson.id); }
function connectObject(id) {
  selectedObject=id; world.highlight(id);
  document.querySelectorAll('[data-link]').forEach(el=>el.classList.toggle('is-linked',el.dataset.link===id));
  const term=lessons[current].terms.find(term=>term.links_to===id);
  const description=$('term-description');
  if(description)description.textContent=term?`${term.term}: ${term.definition}`:'Hover or focus a term to find it in the world.';

}
function setMenu(open) { $('lesson-menu').hidden=!open; $('menu-toggle').setAttribute('aria-expanded',String(open)); }
function renderMenu(){
 $('lesson-list').replaceChildren(...lessons.map((lesson,index)=>{const button=document.createElement('button');button.innerHTML=`<span>${index+1}. ${escapeHTML(lesson.title)}</span>${stateFor(lesson).achieved?icon('check'):''}`;button.setAttribute('aria-current',index===current?'step':'false');button.onclick=()=>{showLesson(index);setMenu(false);$('menu-toggle').focus()};return button;}));
 $('lesson-path').replaceChildren(...lessons.map((lesson,index)=>{const button=document.createElement('button');button.textContent=index+1;button.title=lesson.title;button.setAttribute('aria-label',`Lesson ${index+1}: ${lesson.title}`);button.setAttribute('aria-current',index===current?'step':'false');button.classList.toggle('achieved',stateFor(lesson).achieved);button.onclick=()=>showLesson(index);return button;}));
}
// Which visible shapes the paper describes (with its page) and which are illustrative, from scene.json.
function renderShapeSources(lesson){
  const element=$('shape-sources');
  if(!scene||document.body.classList.contains('is-demo')){element.hidden=true;return;}
  const shown=scene.objects.filter(o=>lesson.scene_state.visible.includes(o.id)), e=escapeHTML, seen=new Set();
  const once=o=>!seen.has(o.label)&&seen.add(o.label);
  const page=o=>[...(evidence?.entities||[]),...(evidence?.figures||[])].find(item=>item.id===o.evidence)?.page;
  const paper=shown.filter(o=>o.basis==='paper').filter(once).map(o=>`${e(o.label)}${page(o)?` <span class="citation">p.${e(page(o))}</span>`:''}`);
  const drawn=shown.filter(o=>o.basis==='hypothesis').filter(once).map(o=>`<span tabindex="0" title="${e(o.rationale)}">${e(o.label)}</span>`);
  const figures=citedFigures(shown);
  const compare=figures.map(f=>`<button class="figure-link" data-figure="${e(f.id)}">${f.caption?`Figure ${e(f.id.replace('fig',''))}`:'The figure'}, p.${e(f.page)}</button>`);
  element.innerHTML=paper.length>6&&compare.length?`<b>Source diagram:</b> ${compare.join(' · ')}`:[paper.length?`<b>Shapes from the paper:</b> ${paper.join(', ')}`:'',drawn.length?`<b>Illustrative:</b> ${drawn.join(', ')}`:'',compare.length?`<b>Compare with</b> ${compare.join(', ')}`:''].filter(Boolean).join(' · ');
  element.querySelectorAll('[data-figure]').forEach(button=>button.onclick=()=>openFigure(figures.find(f=>f.id===button.dataset.figure)));
  element.hidden=!element.innerHTML;
}
// The paper's figures that the visible paper-based shapes cite, directly or through an evidence entity.
function citedFigures(objects){
  const cited=new Set();
  for(const o of objects.filter(o=>o.basis==='paper')){cited.add(o.evidence);const entity=evidence?.entities?.find(item=>item.id===o.evidence);if(entity?.figure)cited.add(entity.figure);}
  return (evidence?.figures||[]).filter(f=>f.image&&cited.has(f.id));
}
function openFigure(figure){
  const caption=figure.caption||'A figure without a numbered caption';
  $('figure-image').src=`${base}${figure.image}`;$('figure-image').alt=caption;
  $('figure-caption').textContent=`${caption} (p.${figure.page})`;$('figure-page').href=`${base}paper.pdf#page=${figure.page}`;
  $('figure-viewer').showModal();$('figure-close').focus();
}
function controlMarkup(control,escape){
 const id='control-'+escape(control.symbol),binary=control.min===0&&control.max===1&&control.step===1;
 const choices={source:['I see cats','I like cats'],head:['Head 1','Head 2'],position:['Off','On'],memory:['Disconnected','Connected'],causal:['Off — allow future tokens','On — hide future tokens']};
 const labels=choices[control.symbol]||['Off','On'];
 if(binary)return `<div class="control"><label for="${id}">${escape(control.label)}</label><select id="${id}" data-parameter="${escape(control.symbol)}">${labels.map((label,index)=>`<option value="${index}" ${index===control.default?'selected':''}>${escape(label)}</option>`).join('')}</select><output id="value-${escape(control.symbol)}" hidden>${escape(control.default)}</output></div>`;
 return `<div class="control"><label for="${id}">${escape(control.label)}<output id="value-${escape(control.symbol)}">${escape(control.default)} ${escape(control.units)}</output></label><input id="${id}" data-parameter="${escape(control.symbol)}" type="range" min="${escape(control.min)}" max="${escape(control.max)}" step="${escape(control.step)}" value="${escape(control.default)}"><div class="range-ends"><span>${escape(control.min)} ${escape(control.units)}</span><span>${escape(control.max)} ${escape(control.units)}</span></div></div>`;
}
function renderLesson(){
  const lesson=lessons[current], saved=stateFor(lesson), e=escapeHTML;
  $('lesson-content').innerHTML=`<p class="lesson-number">Lesson ${String(current+1).padStart(2,'0')} <span class="citation">/ ${String(lessons.length).padStart(2,'0')}</span></p>
  <h1>${e(lesson.title)}</h1>
  <p class="intro">${lesson.intro.map((sentence,index)=>`<span class="sentence linked-term" tabindex="0" data-link="${e(lesson.intro_links[index])}">${e(sentence)}</span>`).join(' ')} <span class="citation">${citation(lesson.source.kind,lesson.source.page)}</span></p>
  <div class="equation-card"><div class="equation-math" role="region" aria-label="Equation" tabindex="0" data-latex="${e(lesson.equation.latex)}"></div><div class="symbols">${lesson.equation.symbols.map(symbol=>`<button class="symbol linked-term" data-link="${e(symbol.links_to)}"><b data-latex="${e(symbol.symbol)}"></b><span>${e(symbol.meaning)}</span></button>`).join('')}</div></div>
  <div class="glossary"><h2>Meet the parts</h2><div class="terms">${lesson.terms.map(term=>`<button class="term linked-term" data-link="${e(term.links_to)}">${e(term.term)}</button>`).join('')}</div><p id="term-description" class="term-description">Hover or focus a term to find it in the world.</p></div>
  <section class="prediction"><h2>Before you try it, predict.</h2><p id="predict-question">${e(lesson.predict.question)}</p><div class="options" role="radiogroup" aria-labelledby="predict-question">${lesson.predict.options.map((option,index)=>`<button class="option" role="radio" aria-checked="${saved.prediction===index}" data-option="${index}"><span class="checkbox" aria-hidden="true">${saved.prediction===index?'✓':''}</span>${e(option)}</button>`).join('')}</div></section>
  <div class="reveal ${saved.revealed?'open':''}"><button class="reveal-trigger" id="reveal-trigger" aria-expanded="${saved.revealed}" aria-controls="why-answer" ${saved.prediction===null?'disabled':''}><span><span class="why-label">Why?</span>Reveal the explanation.</span><small>${saved.prediction===null?'Predict first':'↑'}</small></button><div class="why-wrapper"><div class="why-body"><p id="why-answer" ${saved.revealed?'':'hidden'}><span class="why-result"></span> ${e(lesson.predict.why)} <span class="citation">${citation(lesson.source.kind,lesson.predict.page)}</span></p></div></div></div>
  <section class="controls"><h2>Try it in the world</h2>${lesson.controls.map(control=>controlMarkup(control,e)).join('')}</section>
  <div class="challenge ${saved.achieved?'achieved':''}" id="challenge"><strong>Challenge</strong><span>${e(lesson.challenge.text)}</span><span class="checkmark" aria-label="${saved.achieved?'Achieved':'Not yet achieved'}">${saved.achieved?'✓':'○'}</span></div>
  <p class="source-note">${lesson.source.kind==='paper'?`Source: <cite>${e(lesson.source.title)}</cite>, p.${e(lesson.source.page)}. <a href="${base}paper.pdf#page=${e(lesson.source.page)}" target="_blank" rel="noopener">Read this page ↗</a>`:lesson.source.kind==='simulation'?'From our simulation: the reference model running in your browser, with the same update rule as the checked Python reference.':`Background teaching material from <cite>${e(lesson.source.title)}</cite>.`}</p>`;
  if(lesson.learning){const note=document.createElement('section');note.className='lesson-instructions';note.innerHTML=`<h2>${e(lesson.learning.objective)}</h2><p><strong>Try:</strong> ${e(lesson.learning.action)}</p><p><strong>Watch:</strong> ${e(lesson.learning.observe)}</p><p>${e(lesson.learning.mechanism)}</p>`;$('lesson-content').querySelector('.equation-card')?.before(note);note.after($('lesson-content').querySelector('.controls'));}
  renderMath($('lesson-content'));
  const updateWhy=()=>{$('why-answer').querySelector('.why-result').textContent=saved.prediction===lesson.predict.answer_index?'You called it.':'Here’s what happens.';};
  document.querySelectorAll('[data-option]').forEach(button=>button.onclick=()=>{saved.prediction=Number(button.dataset.option);saved.revealed=false;document.querySelectorAll('[data-option]').forEach(option=>{const active=Number(option.dataset.option)===saved.prediction;option.setAttribute('aria-checked',String(active));option.querySelector('.checkbox').textContent=active?'✓':''});$('reveal-trigger').disabled=false;$('reveal-trigger').setAttribute('aria-expanded','false');$('reveal-trigger').querySelector('small').textContent='↑';document.querySelector('.reveal').classList.remove('open');$('why-answer').hidden=true;updateWhy();saveSession();notify('Prediction selected. You can reveal the explanation.');});
  document.querySelector('.options').onkeydown=event=>{if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const buttons=[...document.querySelectorAll('[data-option]')];const direction=['ArrowDown','ArrowRight'].includes(event.key)?1:-1;const index=(buttons.indexOf(document.activeElement)+direction+buttons.length)%buttons.length;buttons[index].focus();buttons[index].click();};
  $('reveal-trigger').onclick=()=>{saved.revealed=!saved.revealed;$('why-answer').hidden=!saved.revealed;document.querySelector('.reveal').classList.toggle('open',saved.revealed);$('reveal-trigger').setAttribute('aria-expanded',String(saved.revealed));updateWhy();saveSession();};if(saved.revealed)updateWhy();
  document.querySelectorAll('[data-link]').forEach(el=>{el.onpointerenter=()=>connectObject(el.dataset.link);el.onpointerleave=()=>connectObject(null);el.onfocus=()=>connectObject(el.dataset.link);el.onblur=()=>connectObject(null);el.onclick=()=>connectObject(el.dataset.link);});
  document.querySelectorAll('[data-parameter]').forEach(input=>input.oninput=()=>{const symbol=input.dataset.parameter,control=lesson.controls.find(c=>c.symbol===symbol);world.setParams({[symbol]:Number(input.value)});$(`value-${symbol}`).textContent=`${input.value} ${control.units}`;const linked=lesson.equation.symbols.find(s=>s.symbol===symbol);if(linked)connectObject(linked.links_to);});
}
function stopNarration(){narrationGeneration++;if('speechSynthesis'in window)window.speechSynthesis.cancel();narrating=false;$('narrate').setAttribute('aria-pressed','false');$('narrate').setAttribute('aria-label','Narrate lesson');$('narrate').lastElementChild.textContent='Listen';if(world)connectObject(null);}
function showLesson(index){stopNarration();current=index;const lesson=lessons[current];world.setLesson(lesson.scene_state);world.setTeaching?.(lesson.learning);renderLesson();$('lesson-count').textContent=`${String(index+1).padStart(2,'0')} / ${String(lessons.length).padStart(2,'0')}`;$('lesson-title').textContent=lesson.title;$('caption').textContent=lesson.figure_caption;renderShapeSources(lesson);$('previous').disabled=index===0;$('next').disabled=index===lessons.length-1;$('reading').scrollTop=0;$('lesson-content').classList.remove('lesson-transition');void $('lesson-content').offsetWidth;$('lesson-content').classList.add('lesson-transition');renderMenu();saveSession();notify(`Lesson ${index+1}: ${lesson.title}`);}
function togglePlay(){playing=!playing;playing?world.play():world.pause();$('play-toggle').innerHTML=icon(playing?'pause':'play')+`<span>${playing?'Pause':'Play'}</span>`;$('play-toggle').setAttribute('aria-label',playing?'Pause simulation':'Play simulation');$('play-toggle').title=playing?'Pause simulation':'Play simulation';$('clock-status').textContent=playing?'Running':'Paused';$('step').disabled=playing;$('step').querySelector('span').textContent=playing?'Pause to step':'One timestep';}
function narrate(){if(narrating){stopNarration();return;}const generation=++narrationGeneration;const lesson=lessons[current];let index=0;narrating=true;$('narrate').setAttribute('aria-pressed','true');$('narrate').setAttribute('aria-label','Stop narration');$('narrate').lastElementChild.textContent='Stop listening';function next(){if(generation!==narrationGeneration)return;if(index>=lesson.intro.length){stopNarration();return;}const sentence=index++;const utterance=new SpeechSynthesisUtterance(lesson.intro[sentence]);utterance.lang='en-US';utterance.rate=.91;utterance.onstart=()=>{if(generation===narrationGeneration)connectObject(lesson.intro_links[sentence]);};utterance.onend=next;utterance.onerror=event=>{if(generation!==narrationGeneration)return;stopNarration();if(event.error!=='canceled'&&event.error!=='interrupted')toast('Your browser could not play narration. Check voice availability or audio permissions.');};speechSynthesis.speak(utterance);}next();}

function toggleExplore(){exploring=!exploring;document.body.classList.toggle('exploring',exploring);$('explore-toggle').setAttribute('aria-pressed',String(exploring));$('explore-toggle').setAttribute('aria-label',exploring?'Leave explore mode':'Enter explore mode');$('explore-controls').hidden=!exploring;$('explore-toggle').innerHTML=icon(exploring?'collapse':'expand')+`<span id="explore-label">${exploring?'Exit focus':'Focus view'}</span>`;$('world').dispatchEvent(new CustomEvent('explorechange',{detail:{enabled:exploring}}));}
function bindControls(){
 $('previous').onclick=()=>showLesson(current-1);$('next').onclick=()=>showLesson(current+1);$('play-toggle').onclick=togglePlay;
 $('menu-toggle').onclick=()=>setMenu($('lesson-menu').hidden);$('step').onclick=()=>{world.step();notify('Advanced one model timestep.');};$('restart').onclick=()=>{progress.delete(lessons[current].id);showLesson(current);setMenu(false);};
 $('narrate').onclick=narrate;if(!('speechSynthesis'in window)){ $('narrate').disabled=true;$('narrate').title='Narration is not supported by this browser'; }
 $('explore-toggle').onclick=toggleExplore;
 window.addEventListener('app-themechange',event=>$('world').dispatchEvent(new CustomEvent('themechange',{detail:event.detail})));
 $('figure-close').onclick=()=>$('figure-viewer').close();
 $('ask-open').onclick=()=>{stopNarration();$('tutor').showModal();$('question').focus();};$('ask-close').onclick=()=>{$('tutor').close();$('ask-open').focus();};
 document.addEventListener('keydown',event=>{if(!event.target.closest('input,textarea,button,[role=radio],dialog')&&!$('tutor').open){if(event.code==='Space'){event.preventDefault();togglePlay();}if(event.key==='ArrowRight'&&current<lessons.length-1)showLesson(current+1);if(event.key==='ArrowLeft'&&current>0)showLesson(current-1);}if(event.key==='Escape'){if(!$('lesson-menu').hidden){setMenu(false);$('menu-toggle').focus();}else if(exploring&&!$('tutor').open)toggleExplore();}});
 document.addEventListener('pointerdown',event=>{if(!event.target.closest('#lesson-menu')&&!event.target.closest('#menu-toggle'))setMenu(false);});
 $('ask-form').onsubmit=async event=>{event.preventDefault();const question=$('question').value.trim();if(!question)return;$('question').value='';const me=document.createElement('p');me.className='message me';me.textContent=question;$('messages').append(me);const answer=document.createElement('p');answer.className='message';answer.textContent='Reading the source…';$('messages').append(answer);const submit=$('ask-form').querySelector('button');submit.disabled=true;
 try { if(demo){const reply=await json(`${base}tutor.json`);const found=reply.answers.find(item=>item.keywords.some(keyword=>question.toLowerCase().includes(keyword)));answer.textContent='Demo response · '+(found?found.text:reply.other);}else{const data=await json(`/api/runs/${encodeURIComponent(runId)}/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});answer.textContent=data.answer;} }
 catch(error){answer.textContent=error.message;}finally{submit.disabled=false;$('messages').scrollTop=$('messages').scrollHeight;}
 };
 window.addEventListener('pagehide',stopNarration);
}
async function load(){
 document.body.classList.toggle('is-demo',demo);$('demo-note').hidden=true;
 
 if(demo3d){document.title=`${example.title} · Paper-to-World`;$('explore-controls').querySelector('span').textContent='Drag to orbit · Right-drag to pan · Scroll or pinch to zoom';}
 let sampleRun=false,modality=2;
 if(!demo){const run=await json(`/api/runs/${encodeURIComponent(runId)}`);if(!run.status.done||run.status.error||!run.has_world){location.replace(`/build/${encodeURIComponent(runId)}`);return;}modality=run.plan?.modality==='3d'?3:2;sampleRun=run.demo;if(sampleRun){example=Object.values(demos).find(item=>item.key===run.example);if(example)base=example.base;}if(run.plan?.modality==='3d')$('explore-controls').querySelector('span').textContent='Drag to orbit · Right-drag to pan · Scroll or pinch to zoom';if(sampleRun){document.body.classList.add('is-demo');$('demo-note').hidden=true;}}

 lessons=await json(`${base}lessons.json`);world=demo?await import(`${base}world.js`):await isolatedWorld(base,lessons,modality);
 [scene,evidence]=await Promise.all(['scene.json','evidence.json'].map(name=>json(`${base}${name}`).catch(()=>null)));
 for(const name of ['init','setParams','setLesson','highlight','getState','play','pause','step','onObjectClick'])if(typeof world[name]!=='function')throw new Error(`world.js is missing ${name}()`);
 if(world.dimensionality!==2&&world.dimensionality!==3)throw new Error('world.js must export dimensionality 2 or 3');
 for(const lesson of lessons)challengeFunctions.set(lesson.id,world.challengePassed?()=>world.challengePassed(lesson.id):new Function('state',`"use strict"; return Boolean(${lesson.challenge.check_js});`));
 if(!window.katex)throw new Error('The equation renderer could not load. Reload the page or check the server connection.');
 document.body.classList.add('world-starting');$('loading').hidden=false;$('workspace').inert=true;$('controlbar').inert=true;$('workspace').hidden=false;$('controlbar').hidden=false;$('world-dimension').textContent=`${world.dimensionality}D world`;$('source-link').href=`${base}paper.pdf`;$('paper-label').textContent=example?.title||lessons[0].source.title;document.title=(example?.title||lessons[0].source.title)+' · Paper to World';if(demo||sampleRun){$('ask-open').textContent='Ask about this example';$('tutor').querySelector('h2').textContent='Ask about this example';$('source-link').querySelector('.source-label').textContent='Example notes';$('source-link').setAttribute('aria-label','Open example notes');}
 $('tutor-note').textContent=(demo||sampleRun)?'Prepared answers for this example.':'Answers use the paper and cite its source pages.';
 const saved=readLocal(sessionKey);if(saved&&Array.isArray(saved.progress)){for(const [id,value] of saved.progress)if(lessons.some(lesson=>lesson.id===id))progress.set(id,value);}
 if(world.teachingParts)for(const lesson of lessons)for(const part of world.teachingParts){
   if(!lesson.terms.some(term=>term.links_to===part.link))lesson.terms.push({term:part.name,definition:part.description,links_to:part.link});
 }
 $('world').addEventListener('worlderror',event=>fatal(new Error(event.detail)));
 await world.init($('world'));document.body.classList.remove('world-starting');$('loading').hidden=true;$('workspace').inert=false;$('controlbar').inert=false;world.onObjectClick(id=>connectObject(id));bindControls();showLesson(Math.max(0,Math.min(lessons.length-1,Number(saved?.current)||0)));world.play();
 let lastChallengeCheck=0;function monitor(now){if(now-lastChallengeCheck>150){lastChallengeCheck=now;const lesson=lessons[current],saved=stateFor(lesson);if(!saved.achieved){try{if(challengeFunctions.get(lesson.id)(world.getState())){saved.achieved=true;$('challenge').classList.add('achieved');$('challenge').querySelector('.checkmark').textContent='✓';$('challenge').querySelector('.checkmark').setAttribute('aria-label','Achieved');notify('Challenge achieved. '+lesson.challenge.text);renderMenu();saveSession();}}catch(error){$('challenge').querySelector('.checkmark').textContent='!';$('challenge').title=`Challenge could not be evaluated: ${error.message}`;}}}requestAnimationFrame(monitor);}requestAnimationFrame(monitor);
}
load().catch(fatal);
