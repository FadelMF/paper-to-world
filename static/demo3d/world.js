import {explainNeuron} from '../lesson/neuron-explanation.js';
let explanation;
export const dimensionality = 3;
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { specimenControls, anatomy } from '../lesson/specimen.js';
import {neuronParts, neuronValue} from '../lesson/neuron-parts.js';
export const teachingParts=neuronParts;
const partForObject=id=>neuronParts.find(part=>part.link===id||(id==='spike'&&part.id==='axon')||(id==='rate'&&part.id==='terminals'));

import { DT, createModel, advanceModel, measure } from './model.js';
export { measure };

// Every spike number on screen is this one measurement: spikes in the first 1 s (0–1000 ms) after the last reset,
// the same window as the reference targets (measure(I, tau, 1000)).
const FIRST_SECOND_STEPS = Math.round(1000 / DT);
const ids = ['input', 'membrane', 'axon', 'myelin', 'leak', 'threshold', 'spike', 'rate'];
const names = { input: 'Dendrites', membrane: 'Soma', axon: 'Axon', myelin: 'Myelin', leak: 'Leak', threshold: 'Trigger zone', spike: 'Axon', rate: 'Terminals' };
const anchors = {
  input: [-3.8, 2.15, .2], membrane: [-1.1, 1.15, .65], axon: [3.2, -.8, .1],
  myelin: [1.8, .85, .25], leak: [-2.0, -1.0, .6], threshold: [.1, -.8, .55],
  spike: [3.2, -.8, .1], rate: [5.15, 1.1, .3],
};
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
let container, renderer, scene, camera, orbit, observer, chart, chartContext, inset, insetCount, hint, tools;
let state = createModel(), running = false, accumulator = 0, lastFrame = 0, selected = null, spikesFirstSecond = 0;
let modelBox, modelCenter, peek = null, lastPeek = 0, focusedAnatomy = null;
let visible = new Set(), onClick = () => {}, exploring = false, transitioning = false;
let targetCamera = new THREE.Vector3(3.5, 2.8, 13), targetLook = new THREE.Vector3(.1, 0, 0);
let viewPreset = [3.5, 2.8, 13], history = [], events = [], frameCount = 0;
let objects = {}, tags = {}, leaders = {}, pickable = [], materials = {};
let colors, pulseMaterial, outputCurve, pulses = [], inputParticles = [], inputPaths = [];
let pointerDown = null, lastVisual = 0, drawCount = 0;
let assembly = 0, assemblyTarget = 0;
let renderedSignature='';
let gpuFence=null,lastRender=0,shadowAssembly=-1;
let anatomySelected=null, inspector;
const anatomyMeshes={};
// Container-pixel box of each scene object: its geometry's 3D bounds projected through the camera.
export function objectBounds(){
  if(!renderer)return {};
  const canvas=renderer.domElement.getBoundingClientRect(),host=container.getBoundingClientRect(),corner=new THREE.Vector3(),result={};
  for(const id of ids){
    // A pulse between spikes has no geometry; its anchor on the axon stands in.
    const box=new THREE.Box3().setFromObject(objects[id]);if(box.isEmpty())box.setFromCenterAndSize(V(anchors[id]),new THREE.Vector3(.2,.2,.2));
    let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
    for(let i=0;i<8;i++){corner.set(i&1?box.max.x:box.min.x,i&2?box.max.y:box.min.y,i&4?box.max.z:box.min.z).project(camera);
      const x=(corner.x+1)/2*canvas.width+canvas.left-host.left,y=(1-corner.y)/2*canvas.height+canvas.top-host.top;
      x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y);}
    result[id]={x:x0,y:y0,width:x1-x0,height:y1-y0};
  }
  return result;
}
export function setAssembly(value){inspector?.setAssembly(value);}
let highlightedParts=[];
const exhibitParts = [];
const anatomyTags=[];
const finishes = {input:'#496b78', membrane:'#c4b694', axon:'#b88e4e', myelin:'#d7c8a1', leak:'#8f7449', threshold:'#b88e4e', rate:'#496b78', spike:'#b88e4e'};
const raycaster = new THREE.Raycaster();
const cursor = new THREE.Vector2();
const V = array => new THREE.Vector3(...array);

function readColors() {
  const style = getComputedStyle(container);
  colors = Object.fromEntries(['paper','surface','ink','muted','accent','line'].map(key => [key, style.getPropertyValue(`--${key}`).trim()]));
}
function specimenMaterial(id) {
  const material = new THREE.MeshPhysicalMaterial({ color: finishes[id], roughness: .32, metalness: id==='axon'||id==='leak'?.65:.12, clearcoat: .45, clearcoatRoughness: .25 });
  materials[id] = material;
  return material;
}
function group(id) {
  const g = new THREE.Group(); g.userData.objectId = id; scene.add(g); objects[id] = g;
  specimenMaterial(id); return g;
}
function mesh(id, geometry, position = [0,0,0], scale = [1,1,1]) {
  const m = new THREE.Mesh(geometry, materials[id]);
  m.position.copy(V(position)); m.scale.set(...scale); m.castShadow = true; m.receiveShadow = true;
  m.userData.objectId = id; objects[id].add(m); pickable.push(m);
  return m;
}
function tapered(points, startRadius, endRadius, segments = 22) {
  const curve = new THREE.CatmullRomCurve3(points.map(V));
  const frames = curve.computeFrenetFrames(segments, false), sides = 16;
  const vertices = [], indices = [], uvs = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments, p = curve.getPointAt(t), radius = THREE.MathUtils.lerp(startRadius, endRadius, t);
    for (let j = 0; j <= sides; j++) {
      const angle = j / sides * Math.PI * 2;
      const offset = frames.normals[i].clone().multiplyScalar(Math.cos(angle) * radius).addScaledVector(frames.binormals[i], Math.sin(angle) * radius);
      vertices.push(p.x + offset.x, p.y + offset.y, p.z + offset.z); uvs.push(j / sides, t);
      if (i < segments && j < sides) {
        const a = i * (sides + 1) + j, b = a + sides + 1;
        indices.push(a, a + 1, b, b, a + 1, b + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices); geometry.computeVertexNormals();
  return { geometry, curve };
}
function branch(id, points, radius = .1, tip = .02) {
  const result = tapered(points, radius, tip); mesh(id, result.geometry); return result.curve;
}
function buildNeuron() {
  ids.forEach(group);
  const somaGeometry = new THREE.SphereGeometry(.78, 64, 48, 2.2, Math.PI*1.4);
  const positions = somaGeometry.attributes.position;
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i), y = positions.getY(i), z = positions.getZ(i);
    const r = 1 + .055 * Math.sin(x * 6 + z * 2) * Math.cos(y * 7);
    positions.setXYZ(i, x * r, y * r * .9, z * r);
  }
  somaGeometry.computeVertexNormals(); mesh('membrane', somaGeometry, [-1.1, 0, 0]);
  materials.membrane.side = THREE.DoubleSide;
  function organelle(geometry, position, color, offset, scale=[1,1,1]) {
    const part = mesh('membrane', geometry, position, scale);
    part.material = new THREE.MeshPhysicalMaterial({color, metalness:.25, roughness:.3, clearcoat:.5});
    exhibitParts.push({part, home:part.position.clone(), offset:V(offset)});
    return part;
  }
  const nucleus = organelle(new THREE.SphereGeometry(.35,48,32,2.2,Math.PI*1.4),[-1.1,0,.2],'#789baa',[0,1.5,.8]);
  nucleus.material.side=THREE.DoubleSide;
  const nucleolus = new THREE.Mesh(new THREE.SphereGeometry(.095,24,16),new THREE.MeshStandardMaterial({color:'#b88e4e',metalness:.6,roughness:.25}));
  nucleolus.position.set(.02,.01,.1);nucleus.add(nucleolus);
  for(let i=0;i<8;i++) {
    const a=i*Math.PI/4;
    const mitochondrion=organelle(new THREE.SphereGeometry(1,24,20,2.2,Math.PI*1.4),[-1.1+Math.cos(a)*.53,Math.sin(a)*.49,.22],'#b88e4e',[Math.cos(a)*.6,Math.sin(a)*.7,.7],[.065,.16,.065]);
    mitochondrion.material.side=THREE.DoubleSide;
    mitochondrion.rotation.z=a;
    for(let j=0;j<5;j++) {
      const fold=new THREE.Mesh(new THREE.TorusGeometry(.05,.009,6,14,Math.PI*1.6),new THREE.MeshStandardMaterial({color:'#725d39',roughness:.45}));
      fold.position.set(0,(-.09+j*.045)/.16,.04/.065);fold.scale.set(1/.065,1/.16,1/.065);mitochondrion.add(fold);
    }
  }
  for(let i=0;i<5;i++) {
    organelle(new THREE.TorusGeometry(.39+i*.035,.018,8,48,Math.PI*1.25),[-1.1,-.02,-.12+i*.04],'#789baa',[-.75,-.55,.4]);
    organelle(new THREE.TorusGeometry(.18+i*.025,.021,8,36,Math.PI),[-.75,-.28,.4+i*.035],'#c7a56c',[.55,-.9,.6],[1,.5,1]);
    for(let j=0;j<7;j++) {
      const a=j*.5;
      organelle(new THREE.SphereGeometry(.018,8,6),[-1.1+Math.cos(a)*(.4+i*.035),Math.sin(a)*(.4+i*.035),-.09+i*.04],'#b88e4e',[-.75,-.55,.4]);
    }
  }
  anatomyMeshes.smoothER=[];anatomyMeshes.lysosomes=[];anatomyMeshes.cytoskeleton=[];
  for(let i=0;i<4;i++){
    const path=new THREE.CatmullRomCurve3([V([-.2,0,0]),V([-.08,.06,.03]),V([.06,-.04,.05]),V([.2,.02,0])]);
    const tubule=organelle(new THREE.TubeGeometry(path,24,.014,10,false),[-1.43,-.25+i*.055,.22],'#5d9095',[-1.05,-.65,.5]);
    anatomyMeshes.smoothER.push(tubule);tubule.userData.anatomyId='smoothER';
    const filamentPath=new THREE.CatmullRomCurve3([V([-.4,0,0]),V([-.15,.04,.02]),V([.15,-.02,.01]),V([.4,.03,0])]);
    const filament=organelle(new THREE.TubeGeometry(filamentPath,24,.008,8,false),[-1.1,-.43+i*.045,.05],'#789197',[0,-1.1,.3]);
    anatomyMeshes.cytoskeleton.push(filament);filament.userData.anatomyId='cytoskeleton';
  }
  for(let i=0;i<3;i++){
    const lysosome=organelle(new THREE.SphereGeometry(.07,24,16),[-.75+i*.08,.3-i*.07,.3],'#b28a48',[.75,.8,.5]);
    anatomyMeshes.lysosomes.push(lysosome);lysosome.userData.anatomyId='lysosomes';
  }
  const branches = [
    [[-1.65,.36,0],[-2.3,.8,.2],[-2.9,1.4,.45],[-3.6,1.9,.25]],
    [[-1.8,.03,.1],[-2.5,.15,.7],[-3.3,.4,.95],[-4.1,.2,1.2]],
    [[-1.6,-.45,.0],[-2.3,-.85,.4],[-2.7,-1.5,.6],[-3.4,-1.9,.3]],
    [[-1.2,.65,-.1],[-1.4,1.35,-.4],[-1.9,1.95,-.9],[-1.7,2.6,-1.1]],
    [[-1.45,.1,-.6],[-2.1,.4,-1.2],[-2.9,.2,-1.7],[-3.5,.8,-2.0]],
    [[-1.15,-.5,-.3],[-1.6,-1.1,-.8],[-1.8,-1.8,-1.2],[-2.3,-2.3,-1.3]],
  ];
  branches.forEach((points,index) => {
    const path = branch('input', points, .14, .035); inputPaths.push(path);
    for(let j=2;j<11;j++) {
      const at=path.getPointAt(j/12), tip=at.clone().add(V([-.08,.12*(j%2?1:-1),.12]));
      branch('input',[at.toArray(),at.clone().lerp(tip,.5).toArray(),tip.toArray()],.018,.009);
      mesh('input',new THREE.SphereGeometry(.034,10,8),tip.toArray());
    }
    const endpoint = V(points[3]), joint = V(points[2]);
    const signs = [-1,1];
    signs.forEach(sign => {
      const tip = endpoint.clone().add(new THREE.Vector3(-.7, sign*.48, sign*.45));
      const mid = endpoint.clone().lerp(tip,.55).add(new THREE.Vector3(0,.1,-.12));
      branch('input', [joint.toArray(), endpoint.toArray(), mid.toArray(), tip.toArray()], .065, .014, 12);
      const twig = mid.clone().add(new THREE.Vector3(-.48, sign*.55, .2));
      branch('input', [endpoint.toArray(), mid.toArray(), twig.toArray()], .035, .009);
    });
  });
  const axonPoints = [[-.4,0,0],[.25,-.1,.05],[1.4,-.18,.18],[2.6,-.3,-.1],[3.8,-.05,-.3],[4.7,.15,-.1]];
  outputCurve = branch('axon', axonPoints, .095, .06);
  const hillock = mesh('threshold', new THREE.ConeGeometry(.24,.72,24), [-.21,-.02,0]);
  hillock.rotation.z = Math.PI/2;
  for (let i = 0; i < 6; i++) {
    const t = .15 + i*.125, at = outputCurve.getPointAt(t), tangent = outputCurve.getTangentAt(t);
    const sheath = mesh('myelin', new THREE.CapsuleGeometry(.16,.26,10,32), at.toArray());
    sheath.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), tangent);
    exhibitParts.push({part:sheath,home:at.clone(),offset:V([0,1.1+(i%2)*.35,0])});
    for(let layer=0;layer<4;layer++) {
      const ring=new THREE.Mesh(new THREE.TorusGeometry(.11+layer*.02,.006,6,32),materials.axon);
      ring.rotation.x=Math.PI/2;ring.position.y=.2;sheath.add(ring);
    }
  }
  for(let i=0;i<5;i++){
    const t=.2125+i*.125,at=outputCurve.getPointAt(t);
    const node=mesh('axon',new THREE.TorusGeometry(.09,.013,8,32),at.toArray());
    node.quaternion.setFromUnitVectors(V([0,0,1]),outputCurve.getTangentAt(t));
  }
  const end = outputCurve.getPointAt(1);
  [[5.45,.85,-.1],[5.6,-.35,.5],[5.3,.15,-1.0]].forEach(tip => {
    const mid = end.clone().lerp(V(tip),.6);
    branch('rate',[end.toArray(),mid.toArray(),tip],.06,.028);
    const bouton=mesh('rate',new THREE.SphereGeometry(.12,24,16),tip);
    for(let i=0;i<5;i++){const vesicle=new THREE.Mesh(new THREE.SphereGeometry(.022,8,8),materials.axon);vesicle.position.set(Math.cos(i*1.26)*.075,Math.sin(i*1.26)*.075,.08);bouton.add(vesicle);}
  });
  [[-1.45,-.36,.61],[-.98,-.43,.62],[-1.2,-.03,.77]].forEach(position => {
    mesh('leak',new THREE.TorusGeometry(.075,.024,7,18),position);
  });
  pulseMaterial = new THREE.MeshBasicMaterial({ color: colors.accent });
  for (let i=0;i<16;i++) {
    const pulse = new THREE.Mesh(new THREE.SphereGeometry(.24,12,10),pulseMaterial);
    pulse.userData.objectId='spike'; pulse.visible=false; scene.add(pulse); pulses.push(pulse); pickable.push(pulse);
  }
  for (let i=0;i<inputPaths.length;i++) {
    const particle = new THREE.Mesh(new THREE.SphereGeometry(.06,10,8),pulseMaterial);
    scene.add(particle); inputParticles.push(particle);
  }
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(30,20),new THREE.ShadowMaterial({opacity:.07}));
  floor.rotation.x=-Math.PI/2; floor.position.y=-2.7; floor.receiveShadow=true; scene.add(floor);
}
function objectId(raw) {
  if(raw==='axon' && visible.has('spike')) return 'spike';
  if(raw==='rate' && !visible.has('rate')) return visible.has('axon')?'axon':'spike';
  if(raw==='threshold' && !visible.has('threshold')) return visible.has('axon')?'axon':'spike';
  return raw;
}
function applySelection() {
  for (const [id,material] of Object.entries(materials)) {
    const active = objectId(id) === selected;
    material.color.set(active ? colors.accent : finishes[id]);
    material.emissive.set(active ? colors.accent : colors.paper);
    material.emissiveIntensity=active ? .08 : .025;
  }
  if(pulseMaterial)pulseMaterial.color.set(colors.accent);
  for(const [id,tag] of Object.entries(tags))tag.classList.toggle('selected',id===selected);
  for(const item of exhibitParts){
    if(item.part.material===materials.myelin)continue;
    item.part.material.emissive.set(anatomyMeshes[anatomySelected]?.includes(item.part)?colors.accent:0x000000);
    item.part.material.emissiveIntensity=.3;
  }
}
function selectAnatomy(id){
  highlightedParts.forEach(({part,original})=>{part.material.dispose();part.material=original;});
  highlightedParts=[];anatomySelected=id;applySelection();
  for(const part of anatomyMeshes[id]||[]){
    highlightedParts.push({part,original:part.material});part.material=part.material.clone();
    part.material.emissive.set(colors.accent);part.material.emissiveIntensity=.35;
  }
  renderedSignature='';
  const teaching=neuronParts.find(part=>part.id===id);
  if(teaching)choose(teaching.link);
}
function focusAnatomy(id){
  selectAnatomy(id);
  const part=anatomyMeshes[id]?.[0];if(!part)return;
  focusedAnatomy=id;
  const point=id==='axon'?outputCurve.getPointAt(.5):id==='dendrites'?inputPaths[0].getPointAt(.55):part.getWorldPosition(new THREE.Vector3());
  orbit.target.copy(point);
  const distance={soma:3,nucleus:2,nucleolus:1,mitochondria:1.3,er:2.6,smoothER:1.4,ribosomes:.5,golgi:1.5,lysosomes:.8,cytoskeleton:2.5,threshold:1.8,leak:1.8,myelin:2,nodes:1.2,terminals:1.4,vesicles:.6}[id]||7;
  targetCamera.copy(point).add(V([.35,.3,3]).setLength(distance));
  orbit.minDistance=.35;transitioning=true;
}
export function highlight(id) { selected=id; if(renderer)applySelection(); }
export function onObjectClick(callback) { onClick=callback; }
function choose(id) { highlight(id); onClick(id); }
const steps = () => Math.round(state.time / DT);
function spikeWindow() { return `${spikesFirstSecond} spikes · 0–${Math.min(1000, Math.floor(state.time))} ms`; }
function value(id) {
  if(id==='input')return `${state.I.toFixed(1)} nA`;
  if(id==='membrane')return `${state.V.toFixed(1).replace('-','−')} mV`;
  if(id==='axon'||id==='spike')return spikeWindow();
  if(id==='myelin')return '6 sheaths';
  if(id==='leak')return `τ ${state.tau.toFixed(0)} ms`;
  if(id==='threshold')return '−50 mV';
  return steps()>=FIRST_SECOND_STEPS?`${spikesFirstSecond} Hz · 0–1000 ms`:`measuring · ${Math.floor(state.time)} of 1000 ms`;
}
function sceneHeight() { return container.clientHeight - (inset.hidden ? 0 : inset.offsetHeight + 8); }
function screen(point, w, h) { const p = point.clone().project(camera); return { x: (p.x*.5+.5)*w, y: (-p.y*.5+.5)*h }; }
// Labels start outward from the model's projected centre and are pushed apart until no two overlap.
function placeLabels(boxes, w, h) {
  const top = 44, pad = 4;
  for (let pass = 0; pass < 30; pass++) {
    let moved = false;
    for (const b of boxes) { b.x = THREE.MathUtils.clamp(b.x, b.w/2+6, w-b.w/2-6); b.y = THREE.MathUtils.clamp(b.y, top+b.h/2, h-b.h/2-6); }
    for (let i = 0; i < boxes.length; i++) for (let j = i+1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      const ox = (a.w+b.w)/2+pad-Math.abs(a.x-b.x), oy = (a.h+b.h)/2+pad-Math.abs(a.y-b.y);
      if (ox <= 0 || oy <= 0) continue;
      moved = true;
      if (oy <= ox) { const s = a.y <= b.y ? 1 : -1; a.y -= s*oy/2; b.y += s*oy/2; }
      else { const s = a.x <= b.x ? 1 : -1; a.x -= s*ox/2; b.x += s*ox/2; }
    }
    if (!moved) break;
  }
}
function overlay() {explanation?.update();
  const w=container.clientWidth,h=sceneHeight(),center=screen(modelCenter,w,h),boxes=[];
  const exploded=assembly>0;
  inspector.update();
  for(const id of ids) {
    const part=partForObject(id),tag=tags[id],leader=leaders[id],shown=exploded?id!=='spike':visible.has(id)||id===peek;
    tag.hidden=!shown; leader.hidden=!shown; tag.classList.toggle('peek',!exploded&&shown&&!visible.has(id));
    if(!shown)continue;
    const label=exploded?`${neuronParts.indexOf(part)+1} ${part.name}`:names[id];
    const live=exploded?neuronValue(part.id,{...state,spikesFirstSecond}):value(id);
    tag.querySelector('.tag-name').textContent=label;
    tag.querySelector('.tag-value').textContent=live;
    tag.setAttribute('aria-label',`${label}: ${live}`);
    if(exploded)tag.dataset.part=part.id;else delete tag.dataset.part;
    const anchor=V(anchors[id]);if(id==='myelin')anchor.y+=assembly*1.2;
    if(id==='membrane'){anchor.y-=assembly*2.1;anchor.x-=assembly*.8;}
    const p=screen(anchor,w,h),tw=tag.offsetWidth,th=tag.offsetHeight;
    let dx=p.x-center.x,dy=p.y-center.y;const length=Math.hypot(dx,dy);
    if(length<1){dx=0;dy=-1;}else{dx/=length;dy/=length;}
    boxes.push({id,px:p.x,py:p.y,x:p.x+dx*(24+tw/2),y:p.y+dy*(16+th/2),w:tw,h:th});
  }
  placeLabels(boxes,w,h);
  for(const box of boxes) {
    tags[box.id].style.left=`${box.x}px`;tags[box.id].style.top=`${box.y}px`;
    const leader=leaders[box.id],dx=box.x-box.px,dy=box.y-box.py;
    leader.style.left=`${box.px}px`;leader.style.top=`${box.py}px`;
    leader.style.width=`${Math.hypot(dx,dy)}px`;leader.style.transform=`rotate(${Math.atan2(dy,dx)}rad)`;
  }
  anatomyTags.forEach(({tag,part,id})=>{
    tag.hidden=assembly<.7||h<330||anatomySelected!==id;if(tag.hidden)return;
    const p=screen(part.getWorldPosition(new THREE.Vector3()),w,h);
    const tw=tag.offsetWidth,th=tag.offsetHeight;
    let best=null;
    for(let x=tw/2+8;x<w-tw/2-8;x+=18)for(let y=44+th/2;y<h-th/2-6;y+=18){
      if(boxes.some(box=>Math.abs(x-box.x)<(tw+box.w)/2+6&&Math.abs(y-box.y)<(th+box.h)/2+6))continue;
      const cost=(x-p.x)**2+(y-p.y)**2;
      if(!best||cost<best.cost)best={x,y,cost};
    }
    if(best){tag.style.left=`${best.x}px`;tag.style.top=`${best.y}px`;}
    else tag.hidden=true;
  });
  if(!inset.hidden)insetCount.textContent=spikeWindow();
}
function trace() {
  if(inset.hidden)return;
  const bounds=chart.getBoundingClientRect(),dpr=Math.min(devicePixelRatio,2);
  if(chart.width!==Math.round(bounds.width*dpr)||chart.height!==Math.round(bounds.height*dpr)){chart.width=Math.round(bounds.width*dpr);chart.height=Math.round(bounds.height*dpr);}
  const c=chartContext,w=bounds.width,h=bounds.height;
  c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,w,h);
  // −70…−45 mV keeps rest and threshold far apart; spikes (+20 mV markers) are drawn as ticks to the top edge.
  const left=30,right=w-2,top=2,bottom=h-14,start=Math.max(0,state.time-300);
  const Y=v=>bottom-(THREE.MathUtils.clamp(v,-70,-45)+70)/25*(bottom-top);
  c.strokeStyle=colors.line;c.lineWidth=1;c.setLineDash([3,3]);c.beginPath();c.moveTo(left,Y(-50));c.lineTo(right,Y(-50));c.stroke();c.setLineDash([]);
  c.font='10px Inter, Arial';c.fillStyle=colors.muted;c.textAlign='right';
  c.textBaseline='bottom';c.fillText('−50',left-4,Y(-50)+1);c.textBaseline='top';c.fillText('−65',left-4,Y(-65)-1);
  c.textBaseline='bottom';c.textAlign='left';c.fillText(`${Math.floor(start)} ms`,left,h);c.textAlign='right';c.fillText(`${Math.floor(state.time)} ms`,right,h);
  c.strokeStyle=colors.ink;c.lineWidth=1.3;c.beginPath();history.forEach(([t,v],index)=>{const x=left+(t-start)/300*(right-left);index?c.lineTo(x,Y(v)):c.moveTo(x,Y(v));});c.stroke();
}
function resetModel(){state=createModel({I:state.I,tau:state.tau});history=[];events=[];accumulator=0;spikesFirstSecond=0;}
function updateModel(){
  const before=state.spikes;advanceModel(state);
  if(steps()<=FIRST_SECOND_STEPS)spikesFirstSecond=state.spikes;
  if(state.spikes>before){history.push([state.time,20]);events.push(state.time);}
  history.push([state.time,state.V]);
  while(history.length&&history[0][0]<state.time-300)history.shift();
  // Transit is an illustrative 60 ms animation, not a cable-equation calculation.
  events=events.filter(time=>state.time-time<60);
}
function updateParticles(){
  pulses.forEach((pulse,index)=>{
    pulse.visible=index<events.length;
    if(pulse.visible){const t=(state.time-events[index])/60;pulse.position.copy(outputCurve.getPointAt(Math.min(1,t)));pulse.scale.setScalar(1+.2*Math.sin(t*Math.PI));}
  });
  inputParticles.forEach((particle,index)=>{
    particle.visible=state.I>0;
    if(particle.visible){const t=1-((state.time/90+index*.19)%1);particle.position.copy(inputPaths[index].getPointAt(t));}
  });
}
// Fit the whole neuron into the canvas from the lesson's view direction, leaving room around it for labels.
function cameraPosition(preset){
  const direction=V(preset).sub(targetLook).normalize(),probe=camera.clone();
  const corners=[0,1,2,3,4,5,6,7].map(i=>new THREE.Vector3(i&1?modelBox.max.x:modelBox.min.x,i&2?modelBox.max.y:modelBox.min.y,i&4?modelBox.max.z:modelBox.min.z));
  let distance=14;
  for(let pass=0;pass<5;pass++){
    probe.position.copy(modelCenter).addScaledVector(direction,distance);probe.lookAt(modelCenter);probe.updateMatrixWorld();
    let extent=0;for(const corner of corners){const p=corner.clone().project(probe);extent=Math.max(extent,Math.abs(p.x)/.84,Math.abs(p.y)/.74);}
    distance*=extent;
  }
  return modelCenter.clone().addScaledVector(direction,distance);
}
function resetView(){focusedAnatomy=null;targetCamera.copy(cameraPosition(viewPreset));transitioning=true;orbit.target.copy(modelCenter);}
function layoutScene(){
  const w=container.clientWidth,h=sceneHeight();
  renderer.setSize(w,h,false);renderer.domElement.style.height=`${h}px`;camera.aspect=w/h;camera.updateProjectionMatrix();if(!focusedAnatomy)resetView();
}
export function setLesson(lesson){focusedAnatomy=null;explanation?.setLesson(lesson.params);
  visible=new Set(lesson.visible);Object.assign(state,lesson.params);viewPreset=[...lesson.camera];resetModel();selected=null;
  objects.leak.visible=visible.has('leak');
  inset.hidden=!visible.has('threshold');container.classList.toggle('has-plot',!inset.hidden);
  inspector?.close();selectAnatomy(null);layoutScene();applySelection();
}
export function setParams(params){Object.assign(state,params);resetModel();updateParticles();overlay();trace();}
export function play(){running=true;lastFrame=0;}
export function pause(){running=false;accumulator=0;}
export function step(){if(!running){updateModel();updateParticles();overlay();trace();renderer.render(scene,camera);}}
export function getState(){
  return {...state,spikesFirstSecond,firstSecondDone:steps()>=FIRST_SECOND_STEPS,assembly,assemblyTarget,assemblyPositions:exhibitParts.map(({part})=>part.position.toArray()),anatomySelected,anatomyInventory:Object.keys(anatomyMeshes),anatomicalParts:exhibitParts.length,selectedObject:selected,dimensionality:3,renderer:'three.js',webglVersion:renderer?renderer.getContext().getParameter(renderer.getContext().VERSION):null,
    camera:camera?camera.position.toArray():[],target:orbit?orbit.target.toArray():[],cameraTransitioning:transitioning,drawCalls:drawCount,frames:frameCount,
    pulsePositions:pulses.filter(p=>p.visible).map(p=>p.position.toArray()),meshCount:pickable.length};
}
function pick(event){
  if(!pointerDown||Math.hypot(event.clientX-pointerDown.x,event.clientY-pointerDown.y)>6)return;
  const rect=renderer.domElement.getBoundingClientRect();
  cursor.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
  raycaster.setFromCamera(cursor,camera);
  const hit=raycaster.intersectObjects(pickable,false).find(hit=>hit.object.visible&&hit.object.parent.visible);
  if(hit){if(hit.object.userData.anatomyId){inspector.show(hit.object.userData.anatomyId);return;}inspector.show(partForObject(hit.object.userData.objectId).id);}
}
function addTools(){
  tools=document.createElement('div');tools.className='world-tools';
  const actions=[['↶','Rotate left',()=>rotate(-.3,0)],['↷','Rotate right',()=>rotate(.3,0)],['↑','Tilt up',()=>rotate(0,-.2)],['−','Zoom out',()=>dolly(1.2)],['+','Zoom in',()=>dolly(1/1.2)],['↺','Reset 3D view',resetView]];
  actions.forEach(([text,label,action])=>{const button=document.createElement('button');button.textContent=text;button.setAttribute('aria-label',label);button.title=label;button.onclick=action;tools.append(button);});container.append(tools);
}
function rotate(theta,phi){transitioning=false;const spherical=new THREE.Spherical().setFromVector3(camera.position.clone().sub(orbit.target));spherical.theta+=theta;spherical.phi=THREE.MathUtils.clamp(spherical.phi+phi,.15,Math.PI-.15);camera.position.copy(new THREE.Vector3().setFromSpherical(spherical).add(orbit.target));orbit.update();}
function dolly(factor){transitioning=false;const offset=camera.position.clone().sub(orbit.target);offset.setLength(THREE.MathUtils.clamp(offset.length()*factor,orbit.minDistance,orbit.maxDistance));camera.position.copy(orbit.target).add(offset);orbit.update();}
function frame(now){
  const dt=lastFrame?Math.min(1000,now-lastFrame):0;lastFrame=now;
  assembly=reducedMotion?assemblyTarget:assembly+Math.sign(assemblyTarget-assembly)*Math.min(Math.abs(assemblyTarget-assembly),dt/400);
  if(Math.abs(assemblyTarget-assembly)<.001)assembly=assemblyTarget;
  exhibitParts.forEach(({part,home,offset})=>part.position.copy(home).addScaledVector(offset,assembly));
  objects.leak.visible=assembly>0||visible.has('leak');
  if(running){accumulator+=dt*.12;while(accumulator>=DT){updateModel();accumulator-=DT;}}
  if(transitioning){camera.position.lerp(targetCamera,reducedMotion?1:1-Math.exp(-dt/180));if(camera.position.distanceTo(targetCamera)<.005)transitioning=false;}
  orbit.update();updateParticles();
  const signature=[state.time,assembly,selected,colors.paper,container.clientWidth,container.clientHeight,...camera.position.toArray().map(v=>v.toFixed(4)),...orbit.target.toArray().map(v=>v.toFixed(4))].join('|');
  const gl=renderer.getContext();
  const gpuReady=!gpuFence||gl.clientWaitSync(gpuFence,0,0)!==gl.TIMEOUT_EXPIRED;
  if(signature!==renderedSignature&&gpuReady&&now-lastRender>=33){
    if(gpuFence)gl.deleteSync(gpuFence);
    renderer.shadowMap.needsUpdate=shadowAssembly!==assembly;
    renderer.render(scene,camera);shadowAssembly=assembly;
    gpuFence=gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE,0);gl.flush();
    drawCount=renderer.info.render.calls;frameCount++;renderedSignature=signature;lastRender=now;
  }
  if(now-lastVisual>40){overlay();trace();lastVisual=now;}
  requestAnimationFrame(frame);
}
export function init(el){explanation=explainNeuron(el,getState);
  container=el;container.classList.add('world-3d');readColors();
  renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.shadowMap.autoUpdate=false;renderer.shadowMap.needsUpdate=true;
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.setClearColor(0x000000,0);
  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.85;
  renderer.domElement.setAttribute('aria-label','Interactive 3D neuron. Drag to rotate; use the labeled buttons to inspect each part.');
  renderer.domElement.dataset.renderer='three-webgl';container.append(renderer.domElement);
  renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();pause();hint.textContent='3D graphics context lost. Reload to continue.';});
  scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(38,1,.1,150);camera.position.copy(targetCamera);
  const environment=new RoomEnvironment();const pmrem=new THREE.PMREMGenerator(renderer);
  scene.environment=pmrem.fromScene(environment,.04).texture;environment.dispose();pmrem.dispose();
  orbit=new OrbitControls(camera,renderer.domElement);orbit.target.copy(targetLook);orbit.enableDamping=true;orbit.dampingFactor=.09;
  orbit.minDistance=5;orbit.maxDistance=60;orbit.enablePan=false;orbit.enableZoom=false;orbit.rotateSpeed=.65;
  orbit.addEventListener('start',()=>transitioning=false);
  scene.add(new THREE.HemisphereLight(0xffffff,0x89a6c4,1.1));
  const key=new THREE.DirectionalLight(0xffffff,1.8);key.position.set(-4,8,7);key.castShadow=true;key.shadow.mapSize.set(1024,1024);
  Object.assign(key.shadow.camera,{left:-8,right:8,top:6,bottom:-6,near:.5,far:30});key.shadow.bias=-.001;scene.add(key);
  buildNeuron();
  modelBox=new THREE.Box3();for(const id of ids)modelBox.expandByObject(objects[id]);modelCenter=modelBox.getCenter(new THREE.Vector3());
  Object.assign(anatomyMeshes,{
    soma:[objects.membrane.children[0]],dendrites:objects.input.children,
    nucleus:[exhibitParts[0].part],nucleolus:[exhibitParts[0].part.children[0]],
    mitochondria:exhibitParts.slice(1,9).map(x=>x.part),
    er:Array.from({length:5},(_,i)=>exhibitParts[9+i*9].part),
    golgi:Array.from({length:5},(_,i)=>exhibitParts[10+i*9].part),
    ribosomes:exhibitParts.slice(9,54).filter((_,i)=>i%9>1).map(x=>x.part),
    threshold:objects.threshold.children,leak:objects.leak.children,axon:objects.axon.children,myelin:objects.myelin.children,
    nodes:objects.axon.children.slice(1),terminals:objects.rate.children.filter(part=>part.geometry.type==='SphereGeometry'),
    vesicles:objects.rate.children.flatMap(x=>x.children),
  });
  for(const id of ['nucleus','nucleolus','mitochondria','er','golgi','ribosomes'])anatomyMeshes[id].forEach(part=>{part.userData.anatomyId=id;});
  for(const [name,index,id] of [['Nucleus · nucleolus',0,'nucleus'],['Mitochondria · cristae',3,'mitochondria'],['Rough ER · ribosomes',9,'er'],['Golgi apparatus',10,'golgi']]) {
    const tag=document.createElement('button');tag.className='object-tag anatomy-tag';tag.textContent=name;tag.hidden=true;
    tag.onclick=()=>inspector.show(id);container.append(tag);anatomyTags.push({tag,part:exhibitParts[index].part,id});
  }
  inspector=specimenControls(container,anatomy,value=>assemblyTarget=value,{select:selectAnatomy,value:id=>neuronValue(id,{...state,spikesFirstSecond}),focus:focusAnatomy,reset:()=>{selectAnatomy(null);resetView();}});
  ids.forEach(id=>{const tag=document.createElement('button');tag.className='object-tag';tag.dataset.object=id;const title=document.createElement('span');title.className='tag-name';title.textContent=names[id];const val=document.createElement('span');val.className='tag-value';tag.append(title,val);tag.onclick=()=>inspector.show(partForObject(id).id);container.append(tag);tags[id]=tag;
    const leader=document.createElement('span');leader.className='tag-leader';container.append(leader);leaders[id]=leader;});
  hint=document.createElement('span');hint.className='scene-hint';hint.textContent='3D · Drag to rotate · Click to inspect';container.append(hint);
  inset=document.createElement('div');inset.className='voltage-inset';inset.hidden=true;
  const title=document.createElement('p');title.innerHTML='<span>Membrane potential (mV)</span><b></b>';insetCount=title.querySelector('b');chart=document.createElement('canvas');chart.setAttribute('aria-label','Live membrane voltage trace');chartContext=chart.getContext('2d');inset.append(title,chart);container.append(inset);addTools();
  renderer.domElement.addEventListener('pointerdown',event=>{pointerDown={x:event.clientX,y:event.clientY};});
  renderer.domElement.addEventListener('pointerup',pick);
  // Labels outside the current lesson appear while the pointer is over their part.
  renderer.domElement.addEventListener('pointermove',event=>{
    if(event.buttons||event.timeStamp-lastPeek<80)return;lastPeek=event.timeStamp;
    const rect=renderer.domElement.getBoundingClientRect();
    cursor.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(cursor,camera);
    const hit=raycaster.intersectObjects(pickable,false).find(hit=>hit.object.visible&&hit.object.parent.visible),id=hit?.object.userData.objectId;
    peek=id&&ids.includes(id)&&!visible.has(id)?id:null;
  });
  renderer.domElement.addEventListener('pointerleave',()=>{peek=null;});
  container.addEventListener('themechange',()=>{readColors();applySelection();});
  container.addEventListener('explorechange',event=>{exploring=event.detail.enabled;orbit.enablePan=exploring;orbit.enableZoom=exploring;hint.textContent=exploring?'3D · Drag to orbit · Pinch to zoom':'3D · Drag to rotate · Click to inspect';if(!exploring)resetView();});
  observer=new ResizeObserver(layoutScene);observer.observe(container);
  applySelection();requestAnimationFrame(frame);
}

export function setTeaching(learning){explanation?.setTeaching(learning);}
