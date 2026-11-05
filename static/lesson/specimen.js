import {enhanceSelects} from '/assets/ui/dropdown.js';
import {neuronInventory} from './neuron-parts.js';
export const anatomy = [
  ...neuronInventory,
  ['nucleus','Nucleus','The nucleus contains the cell’s genetic material.'],
  ['nucleolus','Nucleolus','This structure inside the nucleus participates in ribosome production.'],
  ['mitochondria','Mitochondria & cristae','Mitochondria supply energy; their inner membrane forms folds called cristae.'],
  ['er','Rough endoplasmic reticulum','Membrane folds carry ribosomes involved in protein production.'],
  ['smoothER','Smooth endoplasmic reticulum','A membrane network without ribosomes, involved in lipid production and calcium storage.'],
  ['ribosomes','Ribosomes','These small structures assemble proteins.'],
  ['golgi','Golgi apparatus','Stacked membranes modify and package cellular products.'],
  ['lysosomes','Lysosomes','Membrane-bound compartments contain enzymes that break down cellular material.'],
  ['cytoskeleton','Cytoskeleton','Protein filaments support the cell’s shape and provide routes for intracellular transport.'],
  ['nodes','Nodes of Ranvier','Gaps between myelin segments expose the axon membrane.'],
  ['vesicles','Synaptic vesicles','Small sacs in the terminals store neurotransmitters.'],
];

// inventory: [id, name, description] for each structure this world can inspect.
export function specimenControls(container, inventory, onChange, inspection) {
  const panel = document.createElement('div');
  panel.className = 'specimen-controls';
  panel.setAttribute('aria-label', 'Specimen assembly');
  let target = 0;
  const buttons = [];
  function setAssembly(value){
    if(!Number.isFinite(value))return;
    target=Math.max(0,Math.min(1,value));
    buttons.forEach(([b,v])=>b.setAttribute('aria-pressed',String(v===target)));
    onChange(target);
  }
  for (const [label, value] of [['Assemble', 0], ['Explode', 1]]) {
    const button = document.createElement('button');
    button.textContent = label;
    button.setAttribute('aria-pressed', String(value === target));
    button.onclick = () => setAssembly(value);
    buttons.push([button, value]);
    panel.append(button);
  }
  const toggle=document.createElement('button');toggle.textContent='Anatomy';toggle.setAttribute('aria-expanded','false');
  panel.append(toggle);
  const inspector=document.createElement('section');inspector.className='anatomy-inspector';inspector.hidden=true;inspector.setAttribute('aria-label','Component inspector');
  const shell=document.createElement('div');shell.className='specimen-shell';
  const stage=document.createElement('div');stage.className='specimen-stage';
  container.before(shell);shell.append(stage);stage.append(container,inspector);
  const label=document.createElement('label');label.textContent='Component';
  const select=document.createElement('select');select.setAttribute('aria-label','Anatomical structure');
  inventory.forEach(([id,name])=>{const option=document.createElement('option');option.value=id;option.textContent=name;select.append(option);});
  label.append(select);
  const description=document.createElement('p');description.className='anatomy-description';description.setAttribute('aria-live','polite');
  const live=document.createElement('span');live.className='anatomy-value';
  const heading=document.createElement('span');heading.className='anatomy-field-heading';
  const caption=document.createElement('span');caption.textContent='Component';heading.append(caption,live);label.firstChild.replaceWith(heading);
  const actions=document.createElement('div');actions.className='anatomy-actions';
  const focus=document.createElement('button');focus.textContent='Focus component';focus.onclick=()=>{inspection?.focus(select.value);};
  const overview=document.createElement('button');overview.textContent='Reset view';overview.onclick=()=>{inspection?.reset();};
  const dismiss=document.createElement('button');dismiss.textContent='Close';dismiss.onclick=()=>close(true);
  const content=document.createElement('div');content.className='anatomy-content';content.tabIndex=0;content.setAttribute('role','region');content.setAttribute('aria-label','Component description');content.append(description);
  content.addEventListener('keydown',event=>{if([' ','ArrowDown','ArrowUp','ArrowLeft','ArrowRight','PageDown','PageUp','Home','End'].includes(event.key)){event.stopPropagation();if(content.scrollHeight<=content.clientHeight)event.preventDefault();}});
  actions.append(focus,overview,dismiss);inspector.append(label,content,actions);enhanceSelects(inspector);
  function choose(id){select.value=id;select.uiSelect?.sync();description.textContent=inventory.find(item=>item[0]===id)[2];inspection?.select(id);}
  function show(id=select.value){stage.classList.add('is-inspecting');shell.classList.add('is-inspecting');inspector.hidden=false;toggle.setAttribute('aria-expanded','true');choose(id);update();select.uiSelect?.focus();inspector.scrollTop=0;}
  function close(restoreFocus){inspector.hidden=true;stage.classList.remove('is-inspecting');shell.classList.remove('is-inspecting');toggle.setAttribute('aria-expanded','false');if(restoreFocus)toggle.focus({preventScroll:true});}
  select.onchange=()=>choose(select.value);
  toggle.onclick=()=>inspector.hidden?show():close(true);
  inspector.addEventListener('keydown',event=>{if(event.key==='Escape'){event.stopPropagation();close(true);}});
  container.append(panel);
  function update(){const value=inspection?.value?.(select.value);live.hidden=!value;live.textContent=value||'';}
  return {show,close:()=>close(false),setAssembly,update,panel:inspector};
}
