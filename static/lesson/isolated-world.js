// Only data and a small simulation-control protocol cross the opaque frame boundary.
export async function isolatedWorld(base, lessons, dimensionality) {
  const read = async name => {const response=await fetch(base+name);if(!response.ok)throw new Error('World source could not load');return response.text();};
  const [source,model]=await Promise.all([read('world.js'),read('model.js')]);
  const allowedIds=new Set(lessons.flatMap(l=>l.terms.map(t=>t.links_to)));
  let port, state={}, checks={}, callback=()=>{}, frame;
  const send=(method,...args)=>port?.postMessage({method,args});
  const proxy={dimensionality,getState:()=>state,challengePassed:id=>checks[id]===true,onObjectClick:fn=>{callback=fn;}};
  for(const method of ['setParams','setLesson','setTeaching','highlight','play','pause','step'])proxy[method]=(...args)=>send(method,...args);
  proxy.init=container=>new Promise((resolve,reject)=>{
    frame=document.createElement('iframe');frame.title='Interactive simulation';frame.setAttribute('sandbox','allow-scripts');frame.referrerPolicy='no-referrer';frame.className='isolated-world';
    const origin=location.origin;
    frame.src='/assets/lesson/frame.html';
    const timeout=setTimeout(()=>{frame.remove();port?.close();reject(new Error('The simulation did not start. Reload to try again.'));},45000);
    frame.addEventListener('load',()=>{
      const channel=new MessageChannel();port=channel.port1;
      port.onmessage=({data})=>{
        if(!data||typeof data!=='object')return;
        if(data.type==='ready'){clearTimeout(timeout);resolve();}
        if(data.type==='error'){const message=String(data.message).slice(0,300);clearTimeout(timeout);reject(new Error(message));container.dispatchEvent(new CustomEvent('worlderror',{detail:message}));}
        if(data.type==='state'){try{if(JSON.stringify(data).length<65536){state=data.state||{};checks=data.checks||{};}}catch{}}
        if(data.type==='click'&&(data.id===null||allowedIds.has(data.id)))callback(data.id);
      };
      frame.contentWindow.postMessage({type:'initialize',source,model,lessons,origin,theme:document.documentElement.dataset.theme},'*',[channel.port2]);
    },{once:true});
    container.append(frame);
    for(const type of ['themechange','explorechange'])container.addEventListener(type,event=>send('event',type,event.detail));
    window.addEventListener('pagehide',()=>port?.close(),{once:true});
  });
  return proxy;
}
