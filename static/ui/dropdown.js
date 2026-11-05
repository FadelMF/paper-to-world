let serial=0,opened=null;
const controls=new Set();
function close(restore=false){if(!opened)return;const c=opened;opened=null;c.menu.hidden=true;c.button.setAttribute('aria-expanded','false');c.button.removeAttribute('aria-activedescendant');if(restore)c.button.focus({preventScroll:true});}
document.addEventListener('pointerdown',event=>{if(opened&&!opened.menu.contains(event.target)&&!opened.button.contains(event.target))close();});
document.addEventListener('scroll',event=>{if(opened&&!opened.menu.contains(event.target))opened.place?.();},true);
window.addEventListener('resize',()=>close());
export function enhanceSelects(root=document){
 for(const c of controls)if(!c.select.isConnected){if(opened===c)close();c.menu.remove();controls.delete(c);}
 const selects=[...(root.matches?.('select')?[root]:[]),...root.querySelectorAll('select')];
 for(const select of selects){if(select.uiSelect)continue;
  const id=select.id||`app-select-${++serial}`;select.id=id;
  const wrap=document.createElement('div');wrap.className='app-select';select.before(wrap);wrap.append(select);select.hidden=true;select.tabIndex=-1;
  const button=document.createElement('button');button.type='button';button.id=id+'-trigger';button.className='app-select-trigger';button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',id+'-options');button.innerHTML='<span></span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';wrap.append(button);
  const label=select.labels?.[0];const name=select.getAttribute('aria-label')||label?.childNodes[0]?.textContent?.trim()||'Choose an option';if(label?.htmlFor===id)label.htmlFor=button.id;
  const menu=document.createElement('div');menu.id=id+'-options';menu.className='app-select-options';menu.setAttribute('role','listbox');menu.setAttribute('aria-label',name);menu.hidden=true;document.body.append(menu);
  const options=[];let active=select.selectedIndex,typeahead='',timer;
  const control={select,button,menu};controls.add(control);
  function sync(){button.querySelector('span').textContent=select.selectedOptions[0]?.textContent||'Choose an option';button.setAttribute('aria-label',name+': '+button.querySelector('span').textContent);button.disabled=select.disabled;options.forEach((el,i)=>el.setAttribute('aria-selected',String(i===select.selectedIndex)));}
  function mark(index){active=Math.max(0,Math.min(options.length-1,index));options.forEach((el,i)=>el.classList.toggle('is-active',i===active));button.setAttribute('aria-activedescendant',options[active].id);const el=options[active];if(el.offsetTop<menu.scrollTop)menu.scrollTop=el.offsetTop;else if(el.offsetTop+el.offsetHeight>menu.scrollTop+menu.clientHeight)menu.scrollTop=el.offsetTop+el.offsetHeight-menu.clientHeight;}
  function choose(index){if(select.options[index].disabled)return;select.selectedIndex=index;sync();select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));close(true);}
  [...select.options].forEach((option,index)=>{const el=document.createElement('div');el.id=id+'-option-'+index;el.className='app-select-option';el.setAttribute('role','option');el.setAttribute('aria-selected',String(option.selected));el.setAttribute('aria-disabled',String(option.disabled));el.textContent=option.textContent;el.onpointermove=()=>mark(index);el.onpointerdown=e=>e.preventDefault();el.onclick=()=>choose(index);options.push(el);menu.append(el);});
  function place(){const r=button.getBoundingClientRect(),height=Math.min(260,options.length*42+10),below=innerHeight-r.bottom-12;Object.assign(menu.style,{left:Math.max(8,Math.min(r.left,innerWidth-r.width-8))+'px',width:r.width+'px',maxHeight:Math.min(height,Math.max(120,below<height&&r.top>below?r.top-12:below))+'px',top:below<height&&r.top>below?Math.max(8,r.top-height-6)+'px':r.bottom+6+'px'});}
  control.place=place;
  function open(){if(opened===control){close();return;}close();sync();opened=control;menu.hidden=false;place();button.setAttribute('aria-expanded','true');mark(select.selectedIndex);}
  button.onclick=open;button.onkeydown=event=>{if(['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape'].includes(event.key))event.preventDefault();if(event.key==='Escape'){if(opened===control)event.stopPropagation();close(true);return;}if(event.key==='Tab'){close();return;}if(event.key==='Enter'||event.key===' '){if(opened===control)choose(active);else open();return;}if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){if(opened!==control)open();mark(event.key==='Home'?0:event.key==='End'?options.length-1:active+(event.key==='ArrowDown'?1:-1));return;}if(event.key.length===1){if(opened!==control)open();clearTimeout(timer);typeahead+=event.key.toLowerCase();timer=setTimeout(()=>typeahead='',600);const index=[...select.options].findIndex(o=>o.textContent.toLowerCase().startsWith(typeahead));if(index>=0)mark(index);}};
  select.addEventListener('change',sync);select.addEventListener('input',sync);select.uiSelect={sync,focus:()=>button.focus({preventScroll:true})};sync();
 }
}
