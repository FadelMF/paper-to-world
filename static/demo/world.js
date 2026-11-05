import {explainNeuron} from '../lesson/neuron-explanation.js';
let explanation;
export const dimensionality = 2;
import { specimenControls } from '../lesson/specimen.js';
import {neuronParts, neuronInventory, neuronValue} from '../lesson/neuron-parts.js';
export const teachingParts=neuronParts;
import { DT, createModel, advanceModel, measure } from './model.js';
export { measure };
// Every spike number on screen is this one measurement: spikes in the first 1 s (0–1000 ms) after the last reset,
// the same window as the reference targets (measure(I, tau, 1000)).
const FIRST_SECOND_STEPS=Math.round(1000/DT);
const ids=['input','membrane','leak','threshold','spike','rate','axon'];
const labels={input:'Input',membrane:'Membrane',leak:'Leak',threshold:'Threshold',spike:'Axon',rate:'Firing rhythm',axon:'Axon'};
const parts=neuronInventory;
// Bounds enclose the actual paths below, including stroke widths and input particles.
const partBounds={dendrites:[-283,-233,-39,46],soma:[-147,-159,40,-1],leak:[-112,-18,-74,48],threshold:[18,-87,49,-59],myelin:[44,-85,259,-61],axon:[12,-85,277,-59],terminals:[269,-112,317,-32]};
const partOf={input:'dendrites',membrane:'soma',leak:'leak',spike:'axon',axon:'axon',rate:'terminals'};
let container,canvas,ctx,plotArea,tags={},captions={},leaders={},observer,tools,hint,inspector,inspectorPanel,selected=null,callback=()=>{};
let state=createModel(),running=false,lastTime=0,accumulator=0,history=[],flash=0,spikesFirstSecond=0;
let assembly=0,assemblyTarget=0,anatomySelected=null,focusedPart=null;
let visible=new Set(),opacity=Object.fromEntries(ids.map(id=>[id,0]));
let colors={},exploring=false,zoom=1,pan={x:0,y:0},camera={x:0,y:0,z:6},targetCamera={x:0,y:0,z:6};
let pointers=new Map(),drag=null,pinch=null,dragged=false;
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
const width=()=>container.getBoundingClientRect().width;
const height=()=>Math.max(container.getBoundingClientRect().height,(assembly>0||assemblyTarget>0)&&width()<600?480:0);
const mv=value=>value.toFixed(1).replace('-','−');
const steps=()=>Math.round(state.time/DT);
function partTransform(id){
 const [left,top,right,bottom]=partBounds[id],cx=(left+right)/2,cy=(top+bottom)/2;
 const targetScale=Math.min(1,72/(right-left),100/(bottom-top));
 const scale=1+(targetScale-1)*assembly,index=neuronParts.findIndex(part=>part.id===id);
 return {scale,x:assembly*(-300+index*100-cx*targetScale),y:assembly*(-80-cy*targetScale)};
}
const offset=id=>{const {x,y}=partTransform(id);return [x,y];};
const anatomyOpen=()=>!inspectorPanel.hidden;
// Anatomy mode shows the parts; the plot steps aside while it is open (the simulation keeps running).
const shown=id=>visible.has(id);
function readTheme(){const style=getComputedStyle(container);colors=Object.fromEntries(['paper','ink','accent','muted','line','wash','surface'].map(name=>[name,style.getPropertyValue(`--${name}`).trim()]));}
function reset(){state=createModel({I:state.I,tau:state.tau});history=[];accumulator=0;flash=0;spikesFirstSecond=0;}
function modelStep(){const previous=state.spikes;advanceModel(state);if(steps()<=FIRST_SECOND_STEPS)spikesFirstSecond=state.spikes;if(state.spikes>previous){history.push([state.time,20]);flash=1;}history.push([state.time,state.V]);while(history.length&&history[0][0]<state.time-300)history.shift();}
function spikeWindow(){return `${spikesFirstSecond} spikes · 0–${Math.min(1000,Math.floor(state.time))} ms`;}
// Container-pixel box of each scene object, from the part it is drawn as (render check and critic use this).
export function objectBounds(){const parts=Object.fromEntries(screenBounds().map(b=>[b.id,b]));return Object.fromEntries(ids.map(id=>{const {x,y,width,height}=parts[partOf[id]||id];return [id,{x,y,width,height}];}));}
export function setAssembly(value){inspector.setAssembly(value);}
export function getState(){return {...state,spikesFirstSecond,firstSecondDone:steps()>=FIRST_SECOND_STEPS,assembly,assemblyTarget,assemblyPositions:parts.map(item=>offset(item[0])),partBounds:screenBounds(),anatomySelected,anatomyInventory:parts.map(item=>item[0]),anatomyOpen:anatomyOpen(),selectedObject:selected,zoom,panX:pan.x,panY:pan.y};}
export function setParams(obj){Object.assign(state,obj);reset();render();}
export function setLesson(scene){explanation?.setLesson(scene.params);inspector?.close();visible=new Set(scene.visible);Object.assign(state,scene.params);targetCamera={x:scene.camera[0],y:scene.camera[1],z:scene.camera[2]};selected=null;anatomySelected=null;focusedPart=null;zoom=1;pan={x:0,y:0};reset();}
export function highlight(id){selected=id;Object.entries(tags).forEach(([key,tag])=>tag.classList.toggle('selected',key===id));}
export function play(){running=true;lastTime=0;}
export function pause(){running=false;accumulator=0;}
export function step(){if(!running){modelStep();render();}}
export function onObjectClick(fn){callback=fn;}
function choose(id){highlight(id);callback(id);}
function partCenter(id){const [l,t,r,b]=partBounds[id],tr=partTransform(id);return [(l+r)/2*tr.scale+tr.x,(t+b)/2*tr.scale+tr.y];}
function screenBounds(){return neuronParts.map(({id})=>{const [l,t,r,b]=partBounds[id],tr=partTransform(id),a=point(l*tr.scale+tr.x,t*tr.scale+tr.y),z=point(r*tr.scale+tr.x,b*tr.scale+tr.y);return {id,x:a.x,y:a.y,width:z.x-a.x,height:z.y-a.y};});}
function cameraTransform(){
 const plate=!shown('threshold'),side=0,w=width()-2*side,h=height();
 const scale=Math.min(w/((plate?640:700)+330*assembly),plate?Math.max(80,h-85)/310:h/580)*zoom*(6/camera.z);
 const focus=focusedPart?partCenter(focusedPart):[camera.x+40*assembly,camera.y];
 const normal={scale,x:w/2+pan.x-focus[0]*scale,y:h/2+pan.y-focus[1]*scale+(plate&&!focusedPart?80*scale+20:0)};
 const explodedScale=Math.min(width()/720,h/600)*zoom;
 const exploded={scale:explodedScale,x:width()/2+pan.x,y:h*.38+80*explodedScale+pan.y};
 return Object.fromEntries(['scale','x','y'].map(key=>[key,normal[key]+(exploded[key]-normal[key])*assembly]));
}
function point(x,y){const transform=cameraTransform();return {x:transform.x+x*transform.scale,y:transform.y+y*transform.scale};}
function resize(){const dpr=devicePixelRatio||1;canvas.width=Math.round(width()*dpr);canvas.height=Math.round(height()*dpr);render();}
function line(points,id,width=1.5){ctx.strokeStyle=selected===id?colors.accent:colors.ink;ctx.lineWidth=width;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();}
function shifted(id,draw){const tr=partTransform(id);ctx.save();ctx.translate(tr.x,tr.y);ctx.scale(tr.scale,tr.scale);draw();ctx.restore();}
const position={input:[-220,-145],membrane:[-20,0],leak:[-175,40],threshold:[205,92],spike:[230,-100],rate:[250,-15],axon:[230,-100]};
function tagValue(id){switch(id){case'input':return `${state.I.toFixed(1)} nA`;case'membrane':return `${mv(state.V)} mV`;case'leak':return `τ ${state.tau.toFixed(0)} ms`;case'threshold':return '−50 mV';case'spike':case'axon':return spikeWindow();case'rate':return steps()>=FIRST_SECOND_STEPS?`${spikesFirstSecond} Hz · 0–1000 ms`:`measuring · ${Math.floor(state.time)} of 1000 ms`;}}
function drawInput(){ctx.globalAlpha=Math.max(assembly,opacity.input);shifted('dendrites',()=>{line([[-275,-105],[-125,-105]],'input');line([[-137,-112],[-125,-105],[-137,-98]],'input');if(state.I>0){ctx.fillStyle=colors.accent;const p=(state.time/12)%145;ctx.beginPath();ctx.arc(-275+p,-105,3+state.I,0,Math.PI*2);ctx.fill();}});}
// A flat ink schematic: dendrites, soma with nucleus, axon with myelin, terminals. Explode slides the parts along the axis.
function drawMembrane(){
 ctx.globalAlpha=Math.max(assembly,opacity.membrane);
 const curve=(points,width,id)=>{ctx.lineCap='round';ctx.strokeStyle=selected===id?colors.accent:colors.ink;ctx.lineWidth=width;ctx.beginPath();ctx.moveTo(...points[0]);ctx.bezierCurveTo(...points[1],...points[2],...points[3]);ctx.stroke();};
 const roots=[
  [[-112,-101],[-142,-117],[-164,-141],[-193,-163]],
  [[-123,-73],[-158,-69],[-192,-69],[-221,-88]],
  [[-104,-40],[-139,-24],[-166,-3],[-184,21]],
  [[-66,-126],[-74,-154],[-81,-178],[-63,-207]],
  [[-102,-115],[-127,-146],[-139,-177],[-159,-198]]
 ];
 shifted('dendrites',()=>roots.forEach((points,index)=>{
  curve(points,3.2-index*.3,'membrane');
  const end=points[3],joint=points[2];
  for(const sign of [-1,1]){
   const tip=[end[0]-22,index===3?end[1]-17:end[1]+sign*22];
   curve([joint,end,[tip[0]+10,tip[1]],tip],1.3,'membrane');
  }
 }));
 shifted('soma',()=>{ctx.fillStyle=colors.paper;ctx.strokeStyle=selected==='membrane'?colors.accent:colors.ink;ctx.lineWidth=1.6;
 ctx.beginPath();ctx.moveTo(-120,-90);ctx.bezierCurveTo(-123,-135,-55,-157,-29,-118);ctx.bezierCurveTo(12,-143,38,-101,18,-63);ctx.bezierCurveTo(29,-24,-28,-2,-55,-29);ctx.bezierCurveTo(-103,-8,-146,-51,-120,-90);ctx.closePath();ctx.fill();ctx.stroke();
 ctx.fillStyle=colors.wash;ctx.lineWidth=1.2;ctx.beginPath();ctx.ellipse(-62,-80,21,18,-.15,0,Math.PI*2);ctx.fill();ctx.stroke();
 ctx.fillStyle=colors.ink;ctx.beginPath();ctx.arc(-58,-78,4,0,Math.PI*2);ctx.fill();});
 shifted('threshold',()=>{ctx.fillStyle=colors.wash;ctx.strokeStyle=selected==='threshold'?colors.accent:colors.ink;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(20,-85);ctx.lineTo(47,-73);ctx.lineTo(20,-61);ctx.closePath();ctx.fill();ctx.stroke();});
 const outputId=visible.has('axon')?'axon':'spike';
 shifted('axon',()=>{ctx.strokeStyle=selected===outputId?colors.accent:colors.ink;ctx.lineWidth=2.2;ctx.beginPath();ctx.moveTo(14,-74);ctx.bezierCurveTo(95,-65,185,-82,274,-72);ctx.stroke();});
 shifted('terminals',()=>{
  ctx.strokeStyle=selected==='rate'?colors.accent:colors.ink;ctx.lineWidth=1.3;
  for(const [tx,ty] of [[300,-105],[310,-73],[300,-39]]){
   ctx.beginPath();ctx.moveTo(274,-72);ctx.quadraticCurveTo(290,ty,tx,ty);ctx.stroke();
   ctx.fillStyle=colors.paper;ctx.beginPath();ctx.arc(tx,ty,4.5,0,Math.PI*2);ctx.fill();ctx.stroke();
  }
 });
}
function drawLeak(){
 ctx.globalAlpha=Math.max(assembly,opacity.membrane);
 shifted('myelin',()=>{ctx.fillStyle=colors.paper;ctx.strokeStyle=colors.ink;ctx.lineWidth=1.2;for(let i=0;i<6;i++){ctx.beginPath();ctx.roundRect(46+i*37,-83,26,20,8);ctx.fill();ctx.stroke();}});
 ctx.globalAlpha=Math.max(assembly,opacity.leak);shifted('leak',()=>{line([[-82,-16],[-82,21],[-103,21],[-103,44]],'leak');line([[-109,36],[-103,44],[-97,36]],'leak');});
 if(anatomySelected){const [x,y]=partCenter(anatomySelected);ctx.globalAlpha=1;ctx.strokeStyle=colors.accent;ctx.lineWidth=1.5;ctx.setLineDash([4,4]);ctx.beginPath();ctx.arc(x,y,34,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);}
}
function drawSpike(){ctx.globalAlpha=Math.max(assembly,opacity.spike);if(flash>0){shifted('axon',()=>{ctx.fillStyle=colors.accent;ctx.beginPath();ctx.arc(25+(1-flash)*245,-73,5,0,Math.PI*2);ctx.fill();});}}
function drawGraph(){
 ctx.save();if(width()<600)ctx.translate(0,200*assembly);
 ctx.globalAlpha=opacity.threshold;const left=-260,right=260,top=120,bottom=225,scale=cameraTransform().scale;const Y=v=>bottom-(v+75)/105*(bottom-top);
 // Text is sized in screen pixels so tick labels never grow into each other in a small panel.
 const font=size=>`${size/scale}px Inter, Arial`;
 line([[left,top-8],[left,bottom],[right,bottom]],'threshold');
 ctx.save();ctx.setLineDash([4,5]);line([[left,Y(-50)],[right,Y(-50)]],'threshold',1);ctx.restore();
 ctx.font=font(11);ctx.fillStyle=colors.muted;ctx.textAlign='right';
 ctx.textBaseline='bottom';ctx.fillText('−50',left-6/scale,Y(-50)+1/scale);ctx.fillText('+20',left-6/scale,Y(20)+6/scale);
 ctx.textBaseline='top';ctx.fillText('−65',left-6/scale,Y(-65)-1/scale);
 const begin=Math.max(0,state.time-300);ctx.strokeStyle=selected==='rate'||selected==='spike'?colors.accent:colors.ink;ctx.lineWidth=1.5;ctx.beginPath();history.forEach(([t,v],i)=>{const x=left+(t-begin)/300*(right-left);i?ctx.lineTo(x,Y(v)):ctx.moveTo(x,Y(v))});ctx.stroke();
 ctx.textBaseline='top';ctx.textAlign='left';ctx.fillText(`${Math.floor(begin)} ms`,left,bottom+5/scale);ctx.textAlign='right';ctx.fillText(`${Math.floor(state.time)} ms`,right,bottom+5/scale);
 ctx.textAlign='left';ctx.textBaseline='alphabetic';ctx.fillStyle=colors.ink;ctx.font=font(12);ctx.fillText(`Membrane potential (mV) · ${spikeWindow()}`,left,top-16/scale);
 ctx.restore();
}
// Labels and captions start at their anchors and are pushed apart until no two overlap.
// Fixed boxes (the plot, the open inspector) never move; labels are pushed out of them last in every pass.
function placeLabels(boxes,w,h){
 const top=44,pad=4,labels=boxes.filter(b=>!b.fixed),fixed=boxes.filter(b=>b.fixed);
 const overlap=(a,b)=>[(a.w+b.w)/2+pad-Math.abs(a.x-b.x),(a.h+b.h)/2+pad-Math.abs(a.y-b.y)];
 for(let pass=0;pass<60;pass++){
  let moved=false;
  for(const b of labels){b.x=Math.max(b.w/2+6,Math.min(w-b.w/2-6,b.x));b.y=Math.max(top+b.h/2,Math.min(h-b.h/2-6,b.y));}
  for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++){
   const a=labels[i],b=labels[j],[ox,oy]=overlap(a,b);
   if(ox<=0||oy<=0)continue;
   moved=true;
   if(oy<=ox){const s=a.y<=b.y?1:-1;a.y-=s*oy/2;b.y+=s*oy/2;}else{const s=a.x<=b.x?1:-1;a.x-=s*ox/2;b.x+=s*ox/2;}
  }
  for(const a of labels)for(const f of fixed){
   const [ox,oy]=overlap(a,f);
   if(ox<=0||oy<=0)continue;
   moved=true;
   if(oy<=ox)a.y+=a.y<f.y?-oy:oy;else a.x+=a.x<f.x?-ox:ox;
  }
  if(!moved)break;
 }
}
function render(){explanation?.update();
 if(!container)return;const dpr=devicePixelRatio||1;
 if(canvas.width!==Math.round(width()*dpr)||canvas.height!==Math.round(height()*dpr)){canvas.width=Math.round(width()*dpr);canvas.height=Math.round(height()*dpr);}
 canvas.style.height=`${height()}px`;
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width(),height());const tr=cameraTransform();
 container.classList.toggle('is-exploded',assembly>0);
 container.classList.toggle('compact-diagram',width()<600);
 ctx.save();ctx.translate(tr.x,tr.y);ctx.scale(tr.scale,tr.scale);drawInput();drawMembrane();drawLeak();drawSpike();drawGraph();ctx.restore();ctx.globalAlpha=1;
 inspector?.update();
 const teaching=assembly>0;
 if(teaching){
  Object.values(tags).forEach(tag=>tag.hidden=true);
  plotArea.hidden=true;
  renderParts();
  return;
 }
 Object.values(captions).forEach(tag=>tag.hidden=true);
 Object.values(leaders).forEach(leader=>leader.hidden=true);
 const boxes=[];
 for(const id of ids){
  const tag=tags[id];
  tag.hidden=!shown(id)&&opacity[id]<.02;tag.disabled=!shown(id);tag.style.opacity=opacity[id];
  tag.querySelector('.tag-value').textContent=tagValue(id);
  tag.setAttribute('aria-label',`${labels[id]}: ${tagValue(id)}`);tag.classList.toggle('selected',selected===id);
  if(tag.hidden)continue;
  const [dx,dy]=partOf[id]?offset(partOf[id]):[0,0],p=point(position[id][0]+dx,position[id][1]+dy);
  boxes.push({element:tag,x:p.x,y:p.y,w:tag.offsetWidth,h:tag.offsetHeight});
 }
 // The plot (drawn on the canvas) is a fixed obstacle, so no label covers its title or axes.
 plotArea.hidden=opacity.threshold<=.5;
 if(!plotArea.hidden){const a=point(-300,92),b=point(270,250);Object.assign(plotArea.style,{left:`${a.x}px`,top:`${a.y}px`,width:`${b.x-a.x}px`,height:`${b.y-a.y}px`});boxes.push({fixed:true,x:(a.x+b.x)/2,y:(a.y+b.y)/2,w:b.x-a.x,h:b.y-a.y});}
 placeLabels(boxes,width(),height());
 for(const box of boxes.filter(box=>!box.fixed)){box.element.style.left=`${box.x}px`;box.element.style.top=`${box.y}px`;}
}
function renderParts(){
 const bounds=screenBounds(),top=Math.min(...bounds.map(b=>b.y)),bottom=Math.max(...bounds.map(b=>b.y+b.height)),boxes=[];
 const snapshot={...state,spikesFirstSecond};
 neuronParts.forEach((part,index)=>{
  const tag=captions[part.id];tag.hidden=false;
  tag.querySelector('.tag-value').textContent=neuronValue(part.id,snapshot);
  tag.classList.toggle('selected',anatomySelected===part.id||selected===part.link);
  const anchor=point(...partCenter(part.id)),w=tag.offsetWidth,h=tag.offsetHeight;
  const above=index%2===0;
  let box;
  for(let lane=0;!box;lane++){
   const y=above?Math.max(58+h/2,top-28-lane*(h+8)):bottom+28+lane*(h+8);
   const candidates=[Math.max(w/2+8,Math.min(width()-w/2-8,anchor.x)),w/2+8,...boxes.map(b=>b.x+b.w/2+w/2+8)];
   for(const x of candidates){
    if(x+w/2>width()-8)continue;
    if(boxes.some(b=>Math.abs(x-b.x)<(w+b.w)/2+6&&Math.abs(y-b.y)<(h+b.h)/2+6))continue;
    box={x,y,w,h};break;
   }
   // If the upper lanes reach the toolbar, continue below the specimen.
   if(!box&&above&&top-28-(lane+1)*(h+8)<58+h/2){
    box={x:Math.max(w/2+8,Math.min(width()-w/2-8,anchor.x)),y:bottom+28+(lane+2)*(h+8),w,h};
    while(boxes.some(b=>Math.abs(box.x-b.x)<(w+b.w)/2+6&&Math.abs(box.y-b.y)<(h+b.h)/2+6))box.y+=h+8;
   }
  }
  boxes.push(box);tag.style.left=`${box.x}px`;tag.style.top=`${box.y}px`;
  const leader=leaders[part.id],dx=box.x-anchor.x,dy=box.y-anchor.y;leader.hidden=false;
  Object.assign(leader.style,{left:`${anchor.x}px`,top:`${anchor.y}px`,width:`${Math.hypot(dx,dy)}px`,transform:`rotate(${Math.atan2(dy,dx)}rad)`});
 });
 if(assembly>0){
  const centers=neuronParts.map(part=>point(...partCenter(part.id)));
  ctx.globalAlpha=.35*assembly;ctx.strokeStyle=colors.accent;ctx.lineWidth=1;ctx.setLineDash([4,5]);ctx.beginPath();
  centers.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.stroke();ctx.setLineDash([]);
  const end=centers.at(-1);ctx.beginPath();ctx.moveTo(end.x-6,end.y-4);ctx.lineTo(end.x,end.y);ctx.lineTo(end.x-6,end.y+4);ctx.stroke();ctx.globalAlpha=1;
 }
}
function frame(now){
 const elapsed=lastTime?now-lastTime:0,dt=Math.min(elapsed,50);lastTime=now;
 // Explode/assemble takes about 400 ms of real time and is independent of the simulation clock.
 assembly=reducedMotion?assemblyTarget:assembly+Math.sign(assemblyTarget-assembly)*Math.min(Math.abs(assemblyTarget-assembly),elapsed/400);
 if(running){accumulator+=dt*.12;while(accumulator>=DT){modelStep();accumulator-=DT;}flash=Math.max(0,flash-dt/230);}
 const blend=reducedMotion?1:1-Math.exp(-elapsed/160);for(const id of ids)opacity[id]+=(Number(shown(id))-opacity[id])*blend;for(const key of ['x','y','z'])camera[key]+=(targetCamera[key]-camera[key])*blend;render();requestAnimationFrame(frame);
}
function worldPoint(event){const rect=canvas.getBoundingClientRect(),tr=cameraTransform();return{x:(event.clientX-rect.left-tr.x)/tr.scale,y:(event.clientY-rect.top-tr.y)/tr.scale};}
// Which part is under a point, in each part's own (unexploded) coordinates.
function hitPart(p){
 const local=id=>{const tr=partTransform(id);return {x:(p.x-tr.x)/tr.scale,y:(p.y-tr.y)/tr.scale};};
 let trigger=local('threshold');if(trigger.x>=18&&trigger.x<=49&&trigger.y>=-87&&trigger.y<=-59)return 'threshold';
 let q=local('terminals');if(q.x>272&&q.x<318&&q.y>-112&&q.y<-32)return 'terminals';
 q=local('myelin');if(q.x>42&&q.x<246&&q.y>-87&&q.y<-59)return 'myelin';
 q=local('axon');if(q.x>10&&q.x<278&&q.y>-90&&q.y<-55)return 'axon';
 q=local('leak');if((assembly>0||visible.has('leak'))&&q.x>-112&&q.x<-74&&q.y>-18&&q.y<48)return 'leak';
 q=local('soma');if(q.x>-130&&q.x<30&&q.y>-150&&q.y<-15)return 'soma';
 q=local('dendrites');if(q.x>-280&&q.x<-95&&q.y>-215&&q.y<25)return 'dendrites';
 return null;
}
function picking(event){
 if(dragged)return;
 const p=worldPoint(event);
 if(shown('threshold')&&p.y>100&&p.y<235&&Math.abs(p.x)<280){choose('threshold');return;}
 const hit=hitPart(p);if(!hit)return;
 inspector.show(hit);
}
function changeZoom(multiplier){zoom=Math.max(.55,Math.min(2.8,zoom*multiplier));render();}
export function init(el){container=el;explanation=explainNeuron(container,getState);container.classList.add('world-2d');canvas=document.createElement('canvas');canvas.setAttribute('aria-label','Interactive neuron diagram and live membrane voltage trace. Use the labeled object buttons to inspect its parts.');ctx=canvas.getContext('2d');container.append(canvas);for(const id of ids){const tag=document.createElement('button');tag.className='object-tag';tag.dataset.object=id;tag.innerHTML=`<span class="tag-name">${labels[id]}</span><span class="tag-value"></span>`;tag.onclick=()=>inspector.show(id==='threshold'?'threshold':partOf[id]);container.append(tag);tags[id]=tag;}
 neuronParts.forEach(({id,name},index)=>{const caption=document.createElement('button');caption.className='object-tag part-label';caption.dataset.part=id;caption.innerHTML=`<span class="tag-name">${index+1} ${name}</span><span class="tag-value"></span>`;caption.onclick=()=>inspector.show(id);caption.hidden=true;container.append(caption);captions[id]=caption;const leader=document.createElement('span');leader.className='tag-leader';leader.hidden=true;container.append(leader);leaders[id]=leader;});
 hint=document.createElement('span');hint.className='scene-hint';hint.textContent='2D schematic · Click a part to inspect';container.append(hint);
 // Marks where the canvas draws the plot; labels keep out of it.
 plotArea=document.createElement('div');plotArea.className='plot-area';plotArea.setAttribute('aria-hidden','true');container.append(plotArea);
 tools=document.createElement('div');tools.className='world-tools';tools.hidden=true;const actions=[['−','Zoom out',()=>changeZoom(1/1.2)],['+','Zoom in',()=>changeZoom(1.2)],['←','Pan left',()=>pan.x-=30],['→','Pan right',()=>pan.x+=30],['↑','Pan up',()=>pan.y-=30],['↓','Pan down',()=>pan.y+=30],['↺','Reset view',()=>{zoom=1;pan={x:0,y:0};focusedPart=null;}]];for(const[text,label,action]of actions){const b=document.createElement('button');b.textContent=text;b.setAttribute('aria-label',label);b.onclick=()=>{action();render()};tools.append(b);}container.append(tools);
 container.addEventListener('themechange',()=>{readTheme();render();});container.addEventListener('explorechange',event=>{exploring=event.detail.enabled;tools.hidden=!exploring;canvas.style.touchAction=exploring?'none':'auto';hint.textContent=exploring?'2D schematic · Drag to pan · Scroll to zoom':'2D schematic · Click a part to inspect';if(!exploring){zoom=1;pan={x:0,y:0};focusedPart=null;}render();});
 canvas.addEventListener('wheel',event=>{if(!exploring)return;event.preventDefault();changeZoom(event.deltaY>0?.92:1.08);},{passive:false});
 canvas.addEventListener('pointerdown',event=>{dragged=false;if(!exploring)return;pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});canvas.setPointerCapture(event.pointerId);drag={x:event.clientX,y:event.clientY};if(pointers.size===2){const[a,b]=[...pointers.values()];pinch=Math.hypot(a.x-b.x,a.y-b.y);}});
 canvas.addEventListener('pointermove',event=>{if(!exploring||!pointers.has(event.pointerId))return;pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});if(pointers.size===2){const[a,b]=[...pointers.values()],distance=Math.hypot(a.x-b.x,a.y-b.y);if(pinch>0)changeZoom(distance/pinch);pinch=distance;dragged=true;}else if(drag){const dx=event.clientX-drag.x,dy=event.clientY-drag.y;pan.x+=dx;pan.y+=dy;if(Math.abs(dx)+Math.abs(dy)>2)dragged=true;drag={x:event.clientX,y:event.clientY};}});
 const end=event=>{pointers.delete(event.pointerId);drag=null;pinch=null;};canvas.addEventListener('pointerup',end);canvas.addEventListener('pointercancel',end);canvas.addEventListener('click',picking);
 inspector=specimenControls(container,parts,value=>assemblyTarget=value,{select:id=>{anatomySelected=id;choose(neuronParts.find(part=>part.id===id).link);},value:id=>neuronValue(id,{...state,spikesFirstSecond}),focus:id=>{inspector.setAssembly(0);focusedPart=id;zoom=2.2;pan={x:0,y:0};},reset:()=>{anatomySelected=null;focusedPart=null;zoom=1;pan={x:0,y:0};}});
 inspectorPanel=inspector.panel;
 readTheme();observer=new ResizeObserver(resize);observer.observe(container);requestAnimationFrame(frame);
}

export function setTeaching(learning){explanation?.setTeaching(learning);}
