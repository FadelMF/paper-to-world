let initialized=false,activeWorld;
export function getState(){return activeWorld?.getState();}
window.addEventListener('message',async event=>{
  if(initialized||event.source!==parent||event.data?.type!=='initialize'||event.ports.length!==1)return;
  initialized=true;
  const port=event.ports[0],{source,model,lessons,origin,theme}=event.data;
  const post=data=>port.postMessage(data);
  const blob=text=>URL.createObjectURL(new Blob([text],{type:'text/javascript'}));
  try{
    document.documentElement.dataset.theme=theme||'light';
    const modelURL=blob(model);
    // Generated modules use a fixed contract; imports outside these assets stay blocked by CSP.
    const code=source.replace(/(['"])\.\/model\.js\1/g,JSON.stringify(modelURL))
      .replace(/(['"])\.\.\/lesson\/([^'"\n]+)\1/g,(_,q,path)=>JSON.stringify(origin+'/assets/lesson/'+path))
      .replace(/(['"])\/assets\/([^'"\n]+)\1/g,(_,q,path)=>JSON.stringify(origin+'/assets/'+path));
    const world=await import(blob(code));activeWorld=world;
    for(const method of ['init','setParams','setLesson','highlight','getState','play','pause','step','onObjectClick'])if(typeof world[method]!=='function')throw new Error('Missing world method: '+method);
    const checks=lessons.map(l=>[l.id,new Function('state',`"use strict";return Boolean(${l.challenge.check_js});`)]);
    await world.init(document.getElementById('world'));
    world.onObjectClick(id=>post({type:'click',id}));
    const methods=new Set(['setParams','setLesson','setTeaching','highlight','play','pause','step']);
    port.onmessage=({data})=>{
      if(!data||!Array.isArray(data.args))return;
      try{
        if(methods.has(data.method))world[data.method]?.(...data.args);
        if(data.method==='event'&&['themechange','explorechange'].includes(data.args[0])){
          if(data.args[0]==='themechange')document.documentElement.dataset.theme=data.args[1]?.theme||'light';
          document.getElementById('world').dispatchEvent(new CustomEvent(data.args[0],{detail:data.args[1]}));
        }
      }catch(error){post({type:'error',message:error.message});}
    };
    setInterval(()=>{try{const state=world.getState(),result={};for(const[id,check]of checks){try{result[id]=check(state);}catch{result[id]=false;}}post({type:'state',state:JSON.parse(JSON.stringify(state)),checks:result});}catch(error){post({type:'error',message:'The simulation could not report its state.'});}},200);
    post({type:'ready'});
  }catch(error){post({type:'error',message:error.message});}
});
