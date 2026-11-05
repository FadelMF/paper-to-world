const notes={
 rest:{title:'Neuron at rest',action:'Keep input at 0 nA.',why:'At −65 mV with no input, input and leak are both zero.'},
 integration:{title:'Input and membrane leak',action:'Change the input and watch the voltage settle.',why:'Input raises the voltage; membrane leak pulls it toward rest. The time constant controls response speed.'},
 threshold:{title:'Threshold and reset',action:'Watch the voltage reach −50 mV, emit a spike, then reset.',why:'Each threshold crossing emits one spike. The model resets to −65 mV and waits 2 ms.'},
 rhythm:{title:'Firing rhythm',action:'Compare spike counts over the same first 1,000 ms.',why:'Stronger input reaches threshold sooner after each reset, increasing the spike count.'}
};
export function explainNeuron(container,readState){
 if(!document.querySelector('[data-neuron-explanation-style]')){const link=document.createElement('link');link.rel='stylesheet';link.href='/assets/lesson/neuron-explanation.css';link.dataset.neuronExplanationStyle='';document.head.append(link);}
 container.style.minHeight='340px';
 const box=document.createElement('aside');box.className='neuron-explanation';box.setAttribute('aria-label','Neuron simulation state');
 box.innerHTML=`<div class="neuron-summary-heading"><h3 data-field="title"></h3><span class="neuron-condition" data-field="condition"></span></div>
 <p class="neuron-action" data-field="action"></p>
 <dl class="neuron-metrics"><div><dt>Input current</dt><dd><span data-field="input"></span><small>nA</small></dd></div><div><dt>Membrane voltage</dt><dd><span data-field="voltage"></span><small>mV</small></dd></div><div><dt>Spike count</dt><dd class="neuron-spike-value"><span data-field="spikes"></span><p data-field="window"></p></dd></div></dl>
 <details class="neuron-calculation"><summary>How the voltage changes</summary><p data-field="why"></p><dl><div><dt>Input drive · RI</dt><dd><span data-field="drive"></span> mV</dd></div><div><dt>Membrane leak</dt><dd><span data-field="leak"></span> mV</dd></div><div><dt>Rate of change · dV/dt</dt><dd><span data-field="slope"></span> mV/ms</dd></div><div><dt>Firing threshold</dt><dd>−50 mV</dd></div></dl><p class="neuron-model-note">Leaky integrate-and-fire teaching model. Anatomy and pulse travel are illustrative.</p></details>`;
 container.after(box);if(container.closest('#workspace'))document.body.classList.add('neuron-example');
 const fields=Object.fromEntries([...box.querySelectorAll('[data-field]')].map(el=>[el.dataset.field,el]));let mode='rest',teaching=null;
 const set=(key,value)=>{if(fields[key].textContent!==String(value))fields[key].textContent=String(value);};
 const number=(value,digits)=>{const rounded=Number(value.toFixed(digits));return rounded.toFixed(digits).replace('-','−');};
 function update(){const s=readState(),note=notes[mode],drive=10*s.I,leak=-(s.V+65),slope=s.refractory>0?0:(drive+leak)/s.tau;
  set('title',note.title);set('action',note.action);set('condition',s.refractory>0?'Resetting':s.I===0?'At rest':s.spikes>0?'Firing':'Integrating');
  set('input',number(s.I,1));set('voltage',number(s.V,1));set('spikes',s.spikesFirstSecond??s.spikes);
  const elapsed=Math.min(1000,Math.floor(s.time));set('window',elapsed<1000?`${elapsed.toLocaleString()} / 1,000 ms`:'First 1,000 ms');
  set('drive',number(drive,1));set('leak',number(leak,1));set('slope',number(slope,3));set('why',teaching?.mechanism||note.why);
 }
 return {update,setTeaching(value){teaching=value;if(value?.focus){mode=value.focus.includes('rate')?'rhythm':value.focus.includes('threshold')?'threshold':value.focus.includes('leak')?'integration':'rest';}update();},setLesson(params){mode=params.I===0?'rest':params.I<1.5?'integration':params.I<2.5?'threshold':'rhythm';update();}};
}
