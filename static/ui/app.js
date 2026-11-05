import {enhanceSelects} from './dropdown.js';
export {enhanceSelects};
const paths={
 world:'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 6.5c4 2 10 2 14 0M5 17.5c4-2 10-2 14 0"/>',
 home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
 folder:'<path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
 moon:'<path d="M20.5 13A9 9 0 0 1 11 3.5 9 9 0 1 0 20.5 13Z"/>',
 sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
 arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',back:'<path d="M20 12H4m6-6-6 6 6 6"/>',
 upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
 file:'<path d="M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h6"/>',
 cube:'<path d="m12 3 9 5v9l-9 5-9-5V8l9-5Zm0 10 9-5m-9 5-9-5m9 5v9"/>',
 chart:'<path d="M4 3v17h17M7 15l4-5 4 3 5-7"/>',
 play:'<path d="m8 5 11 7-11 7z"/>',pause:'<path d="M8 5v14M16 5v14"/>',
 expand:'<path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>',collapse:'<path d="M3 9h6V3m6 0v6h6M9 21v-6H3m12 6v-6h6"/>',
 volume:'<path d="M4 9h4l5-4v14l-5-4H4zM17 8q4 4 0 8M20 5q7 7 0 14"/>',
 list:'<path d="M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1"/>',
 check:'<path d="m5 12 4 4L19 6"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',
 chat:'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z"/><path d="M8 9h8m-8 4h5"/>',
 refresh:'<path d="M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 13-2l2 3M4 16l2 3a8 8 0 0 0 13-2"/>',
 link:'<path d="m10 14 4-4m-6 6-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 2 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>'
};
export const icon=name=>`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name]||paths.world}</svg>`;
export function readLocal(key,fallback=null){try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}}
export function writeLocal(key,value){try{localStorage.setItem(key,JSON.stringify(value));}catch{}}
export function setTheme(dark){document.documentElement.dataset.theme=dark?'dark':'light';writeLocal('ptw-theme',dark?'dark':'light');document.querySelectorAll('[data-theme-toggle]').forEach(button=>{button.innerHTML=icon(dark?'sun':'moon');button.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');button.title=dark?'Light theme':'Dark theme';});window.dispatchEvent(new CustomEvent('app-themechange',{detail:{dark}}));}
setTheme(readLocal('ptw-theme','light')==='dark');
const header=document.querySelector('[data-app-header]');
if(header){
 const actions=[...header.children];header.replaceChildren();header.className='app-header';
 const brand=document.createElement('a');brand.className='brand';brand.href='/';brand.setAttribute('aria-label','Paper to World — start');brand.innerHTML=icon('world').replace('class="icon"','class="icon brand-mark"')+'<span>Paper to World</span>';
 const nav=document.createElement('nav');nav.className='header-nav';nav.setAttribute('aria-label','Main navigation');nav.innerHTML=`<a href="/" ${location.pathname==='/'?'aria-current="page"':''}>${icon('home')}Start</a><a href="/worlds" ${location.pathname==='/worlds'?'aria-current="page"':''}>${icon('folder')}Your worlds</a>`;
 const context=document.createElement('span');context.className='header-context';context.textContent=header.dataset.section||'';
 const actionGroup=document.createElement('div');actionGroup.className='header-actions';actions.forEach(action=>actionGroup.append(action));
 const theme=document.createElement('button');theme.type='button';theme.className='icon-button';theme.dataset.themeToggle='';theme.onclick=()=>setTheme(document.documentElement.dataset.theme!=='dark');actionGroup.append(theme);
 header.append(brand,nav,context,actionGroup);setTheme(readLocal('ptw-theme','light')==='dark');
}
document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));

enhanceSelects();
new MutationObserver(records=>{let removed=false;for(const record of records){for(const node of record.addedNodes)if(node.nodeType===1&&(node.matches('select')||node.querySelector('select')))enhanceSelects(node);if([...record.removedNodes].some(node=>node.nodeType===1))removed=true;}if(removed)enhanceSelects();}).observe(document.body,{childList:true,subtree:true});


