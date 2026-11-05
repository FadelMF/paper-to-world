import {ids,rows,right,edges} from './architecture.js';
export function makeRenderer(root){
 const canvas=document.createElement('canvas');root.prepend(canvas);const ctx=canvas.getContext('2d');let boxes={};
 return {bounds:()=>boxes,draw(s,visible,assembly,focus,active){
  const w=root.clientWidth,h=root.clientHeight,dpr=devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);const css=getComputedStyle(root),ink=css.getPropertyValue('--muted').trim()||'#526581',accent=css.getPropertyValue('--accent').trim()||'#0866ff';
  const gap=32,margin=8,bw=(w-gap-2*margin)/2,rh=(h-30)/7,bh=Math.min(38,rh-10);boxes={};for(const id of ids)boxes[id]={x:id==='generated'?w*.25:right.has(id)?w/2+gap/2:margin,y:25+rows[id]*rh,width:id==='generated'?w*.5:bw,height:bh};
  for(let i=0;i<edges.length;i++){const [a,b]=edges[i];if(!visible.has(a)||!visible.has(b))continue;const aa=boxes[a],bb=boxes[b],p=[aa.x+aa.width/2,aa.y],q=[bb.x+bb.width/2,bb.y+bb.height];ctx.beginPath();ctx.strokeStyle=i===s.phase?accent:ink;ctx.lineWidth=i===s.phase?2.5:1;ctx.globalAlpha=i===s.phase?1:.45;
   if(right.has(a)===right.has(b)){ctx.moveTo(...p);ctx.lineTo(...q);}else{const ax=right.has(a)?aa.x:aa.x+aa.width,bx=right.has(b)?bb.x:bb.x+bb.width,ay=aa.y+aa.height/2,by=bb.y+bb.height/2;ctx.moveTo(ax,ay);ctx.bezierCurveTo(w/2,ay,w/2,by,bx,by);}ctx.stroke();if(right.has(a)===right.has(b)){ctx.beginPath();ctx.moveTo(q[0],q[1]);ctx.lineTo(q[0]-3,q[1]+5);ctx.lineTo(q[0]+3,q[1]+5);ctx.closePath();ctx.fillStyle=ctx.strokeStyle;ctx.fill();}
   const progress=(s.time% .8)/.8;ctx.fillStyle=accent;if(i===s.phase){ctx.beginPath();ctx.arc(p[0]+(q[0]-p[0])*progress,p[1]+(q[1]-p[1])*progress,3,0,Math.PI*2);ctx.fill();}
  }ctx.globalAlpha=1;
 }};
}
