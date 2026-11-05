// Teaching anatomy shared by the two views of the single-compartment neuron.
export const neuronParts = [
  {id:'dendrites', link:'input', name:'Dendrites / input', description:'Branching inputs collect signals and drive current into the cell body. The model represents their combined input as one current.'},
  {id:'soma', link:'membrane', name:'Soma / membrane', description:'The cell body integrates input. Its membrane holds the one voltage simulated for the whole neuron.'},
  {id:'leak', link:'leak', name:'Membrane leak', description:'Leak pulls the membrane voltage back toward rest. The time constant τ sets how quickly the voltage responds.'},
  {id:'threshold', link:'threshold', name:'Trigger zone / threshold', description:'When the membrane reaches −50 mV, the model records a spike and resets the voltage. This trigger zone is a schematic location for that decision.'},
  {id:'myelin', link:'myelin', name:'Myelin', description:'Six insulating segments wrap the axon in this illustration. They are schematic and do not change the single-compartment simulation.'},
  {id:'axon', link:'axon', name:'Axon / spikes', description:'The axon carries spikes toward the terminals. The count measures spikes in the first 1000 ms after the latest reset; travel along the drawing is illustrative.'},
  {id:'terminals', link:'terminals', name:'Terminals', description:'These branched endings pass signals to other cells. Synaptic transmission is illustrated here, not simulated.'},
];
export function neuronValue(id, state) {
  switch(id) {
    case 'dendrites': return `${state.I.toFixed(1)} nA`;
    case 'soma': return `${state.V.toFixed(1).replace('-', '−')} mV`;
    case 'leak': return `τ ${state.tau.toFixed(0)} ms`;
    case 'threshold': return '−50 mV';
    case 'myelin': return '6 segments · schematic';
    case 'axon': return `${state.spikesFirstSecond} spikes · 0–${Math.min(1000,Math.floor(state.time))} ms`;
    case 'terminals': return '3 endings · schematic';
  }
}
export const neuronInventory = neuronParts.map(({id,name,description})=>[id,name,description]);
