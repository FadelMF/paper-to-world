import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {ids,rows,right,edges,values} from './architecture.js';
export function makeRenderer(root,actions={}){
 const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));root.prepend(renderer.domElement);root.classList.add('spatial-graph');
 const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(36,1,.1,100),orbit=new OrbitControls(camera,renderer.domElement);camera.position.set(9,7,17);orbit.target.set(0,0,0);orbit.enableDamping=false;orbit.enableZoom=false;orbit.enablePan=true;orbit.minDistance=9;orbit.maxDistance=30;
 scene.add(new THREE.HemisphereLight(0xffffff,0x7c91b1,2.3));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(3,9,7);scene.add(light);
 const groups={},slabs={},paths=[];let boxes={},lastSize='',selected=null;
 const slabGeometry=new THREE.BoxGeometry(2.65,.16,1.65),cellGeometry=new THREE.BoxGeometry(1,1,1);const cells={},matrixTransform=new THREE.Object3D(),cellColor=new THREE.Color();
 for(const id of ids){const group=new THREE.Group();scene.add(group);groups[id]=group;const slab=new THREE.Mesh(slabGeometry,new THREE.MeshStandardMaterial({color:right.has(id)?0xa3c4ed:0xd4e2f2,roughness:.42,metalness:.12}));group.add(slab);slabs[id]=slab;group.userData.id=id;
  const tensor=new THREE.InstancedMesh(cellGeometry,new THREE.MeshStandardMaterial({roughness:.38,metalness:.08}),48);tensor.userData.id=id;tensor.instanceMatrix.setUsage(THREE.DynamicDrawUsage);group.add(tensor);cells[id]=tensor;
  slab.userData.id=id;
 }
 for(const [a,b]of edges){const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(),new THREE.Vector3()]),new THREE.LineBasicMaterial({color:0x819dbd,transparent:true,opacity:.5}));scene.add(line);paths.push({line,a,b});}
 const floor=new THREE.GridHelper(14,14,0xc1d1e4,0xe3eaf3);floor.material.transparent=true;floor.material.opacity=.3;floor.position.y=-3.9;scene.add(floor);
 const stackLabels=['Encoder','Decoder'].map(name=>{const el=document.createElement('span');el.className='spatial-stack-label';el.textContent=name;root.append(el);return el;});const valueKey=document.createElement('span');valueKey.className='spatial-value-key';valueKey.textContent='Each cell: one token feature · blue + · amber −';root.append(valueKey);
 const controls=document.createElement('div');controls.className='spatial-tools';controls.innerHTML='<span>Drag to orbit · right-drag to pan</span><button type="button" data-reset>Reset view</button><label>Layer spacing <input data-spacing type="range" min="0" max="100" step="1" value="35" aria-label="Layer spacing"><output>35%</output></label>';root.append(controls);
 controls.querySelector('[data-reset]').onclick=()=>reset();controls.querySelector('[data-spacing]').oninput=e=>{const value=Number(e.target.value);controls.querySelector('output').textContent=value+'%';actions.assemble?.(value/100);};
 function reset(){camera.position.set(9,7,17).normalize().multiplyScalar(root.clientWidth<500?18:15);orbit.target.set(0,0,0);orbit.update();actions.redraw?.();}
 const ray=new THREE.Raycaster(),cursor=new THREE.Vector2();let down;
 renderer.domElement.addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);renderer.domElement.addEventListener('pointerup',e=>{if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const r=renderer.domElement.getBoundingClientRect();cursor.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);ray.setFromCamera(cursor,camera);const hit=ray.intersectObjects(Object.values(groups),true)[0];if(hit?.object.userData.id)actions.select?.(hit.object.userData.id);});
 orbit.addEventListener('change',()=>{renderer.render(scene,camera);});
 function capture(w,h){const out={};for(const id of ids){const box=new THREE.Box3().setFromObject(groups[id]),points=[];for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){const p=new THREE.Vector3(x,y,z).project(camera);points.push([(p.x+1)*w/2,(1-p.y)*h/2]);}const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);out[id]={x:Math.min(...xs),y:Math.min(...ys),width:Math.max(...xs)-Math.min(...xs),height:Math.max(...ys)-Math.min(...ys)};}return out;}
 return {spatial:true,bounds:()=>boxes,resetCamera:reset,setExplore(enabled){orbit.enableZoom=enabled;},getView(){return {camera:camera.position.toArray(),target:orbit.target.toArray(),perspective:true};},draw(s,visible,assembly,focus,active,chosen){
  selected=chosen;const w=root.clientWidth,h=root.clientHeight,narrow=w<520,vx=narrow?0:160,vh=h-(narrow?172:0),vw=w-vx;renderer.setSize(w,h,false);renderer.setViewport(vx,narrow?172:0,vw,vh);camera.aspect=vw/vh;camera.updateProjectionMatrix();
  if(lastSize!==w+':'+h){lastSize=w+':'+h;camera.position.normalize().multiplyScalar(w<500?18:15);}
  for(const id of ids){const group=groups[id],isRight=right.has(id);group.visible=visible.has(id);group.position.set(id==='generated'?0:isRight?3.3:-3.3,id==='generated'?-3.1:(2.5-rows[id])*(.85+assembly*.23),id==='generated'?3.5:isRight?1.15+(5-rows[id])*.25:-1.3-(5-rows[id])*.15);slabs[id].material.color.setHex(selected===id?0x0866ff:focus.includes(id)?0x8db9ee:isRight?0xb7d1ef:0xd5e2f1);
   const matrix=values(s,id),rowCount=matrix.length,colCount=matrix[0].length,tensor=cells[id];tensor.count=Math.min(48,rowCount*colCount);
   for(let index=0;index<tensor.count;index++){const r=Math.floor(index/colCount),c=index%colCount,v=matrix[r][c],cellWidth=2.3/colCount,cellDepth=1.3/rowCount,height=id==='generated'?.23:.04+Math.min(3,Math.abs(v))*.23;matrixTransform.position.set((c-(colCount-1)/2)*cellWidth,.08+height/2,(r-(rowCount-1)/2)*cellDepth);matrixTransform.scale.set(cellWidth*.77,height,cellDepth*.72);matrixTransform.updateMatrix();tensor.setMatrixAt(index,matrixTransform.matrix);cellColor.setHex(v<0?0xb56a24:0x0866ff);if(id===active)cellColor.multiplyScalar(1.15);tensor.setColorAt(index,cellColor);}
   tensor.instanceMatrix.needsUpdate=true;if(tensor.instanceColor)tensor.instanceColor.needsUpdate=true;tensor.computeBoundingBox();tensor.computeBoundingSphere();

  }
  for(let i=0;i<paths.length;i++){const {line,a,b}=paths[i];line.geometry.setFromPoints([groups[a].position,groups[b].position]);line.material.color.setHex(i===s.phase?0x0866ff:0x819dbd);line.material.opacity=i===s.phase?1:.35;}
  orbit.update();renderer.render(scene,camera);stackLabels.forEach((el,i)=>{const pos=new THREE.Vector3(i?3.3:-3.3,i?3.5:2.8,i?1.8:-1.8).project(camera);el.style.left=((pos.x+1)*vw/2+vx)+'px';el.style.top=((1-pos.y)*vh/2)+'px';});boxes=capture(vw,vh);for(const b of Object.values(boxes))b.x+=vx;controls.querySelector('[data-spacing]').value=String(Math.round(assembly*100));controls.querySelector('output').textContent=Math.round(assembly*100)+'%';
 }};
}
