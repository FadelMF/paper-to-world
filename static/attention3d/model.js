export const DT=.1;
const defaults={source:0,position:1,memory:1,prefix:3,causal:1,stage:0,head:0,training_step:4000,input_gain:100,position_gain:100,score_gain:100,memory_gain:100};
const embeddings=Array.from({length:6},(_,i)=>Array.from({length:4},(_,j)=>Math.sin((i+1)*(j+1))*.6));
const weights=(rows,cols,seed)=>Array.from({length:rows},(_,r)=>Array.from({length:cols},(_,c)=>Math.sin((r+1)*(c+1)+seed)*.35));
const matmul=(a,b)=>a.map(row=>b[0].map((_,j)=>row.reduce((s,x,k)=>s+x*b[k][j],0)));
const softmax=row=>{const peak=Math.max(...row),exp=row.map(x=>Math.exp(x-peak)),sum=exp.reduce((a,b)=>a+b,0);return exp.map(x=>x/sum);};
const normAdd=(a,b)=>a.map((ra,i)=>{const row=ra.map((x,j)=>x+b[i][j]),mean=row.reduce((a,b)=>a+b,0)/4,denom=Math.sqrt(row.reduce((s,x)=>s+(x-mean)**2,0)/4+1e-5);return row.map(x=>(x-mean)/denom);});
const embed=(tokens,positional)=>tokens.map((t,i)=>embeddings[t].map((v,d)=>v*2+positional*(d%2===0?Math.sin(i/10000**(2*Math.floor(d/2)/4)):Math.cos(i/10000**(2*Math.floor(d/2)/4)))));
function multihead(query,memory,seed,causal=false,score_gain=100){
 const q=matmul(query,weights(4,4,seed)),k=matmul(memory,weights(4,4,seed+1)),v=matmul(memory,weights(4,4,seed+2)),heads=[],attention=[];
 for(let h=0;h<2;h++){const rows=[],values=[];for(let i=0;i<q.length;i++){const scores=k.map((key,j)=>!causal||j<=i?(q[i][h*2]*key[h*2]+q[i][h*2+1]*key[h*2+1])/Math.sqrt(2)*score_gain/100:-1e9),a=softmax(scores);rows.push(a);values.push([0,1].map(d=>a.reduce((s,w,j)=>s+w*v[j][h*2+d],0)));}heads.push(values);attention.push(rows);}
 const concat=query.map((_,i)=>[...heads[0][i],...heads[1][i]]);return [matmul(concat,weights(4,4,seed+3)),attention,heads,concat];
}
const feedforward=x=>matmul(matmul(x,weights(4,8,18)).map(row=>row.map(v=>Math.max(0,v+.1))),weights(8,4,19));
export function createModel(params={}){
 const p={...defaults,...params},source_ids=[1,p.source===0?2:4,3],embedded=embed(source_ids,p.position*p.position_gain/100).map(row=>row.map(v=>v*p.input_gain/100));
 const [encoder_attention,enc_weights,head_outputs,concat]=multihead(embedded,embedded,1,false,p.score_gain),encoder_norm=normAdd(embedded,encoder_attention),encoder_ff=feedforward(encoder_norm),encoder=normAdd(encoder_norm,encoder_ff);
 const prefix_ids=[0],generated=[];let target_embedded,decoder_self,self_weights,decoder_norm,cross,cross_weights,decoder_ff,decoder,probabilities,predicted;
 for(let n=0;n<p.prefix;n++){
  target_embedded=embed(prefix_ids,p.position*p.position_gain/100);[decoder_self,self_weights]=multihead(target_embedded,target_embedded,7,!!p.causal,p.score_gain);decoder_norm=normAdd(target_embedded,decoder_self);
  [cross,cross_weights]=multihead(decoder_norm,encoder.map(row=>row.map(v=>v*p.memory*p.memory_gain/100)),12,false,p.score_gain);const cross_norm=normAdd(decoder_norm,cross);decoder_ff=feedforward(cross_norm);decoder=normAdd(cross_norm,decoder_ff);probabilities=softmax(matmul([decoder.at(-1)],weights(4,6,23))[0]);predicted=probabilities.indexOf(Math.max(...probabilities));generated.push(predicted);if(generated.length<p.prefix)prefix_ids.push(predicted);
 }
 let future_mass=0;for(const head of self_weights)for(let i=0;i<prefix_ids.length;i++)for(let j=i+1;j<prefix_ids.length;j++)future_mass+=head[i][j];
 return {...p,learning_rate:512**-.5*Math.min(p.training_step**-.5,p.training_step*4000**-1.5),source_ids,prefix_ids,generated,embedded,encoder_queries:matmul(embedded,weights(4,4,1)),encoder_keys:matmul(embedded,weights(4,4,2)),encoder_values:matmul(embedded,weights(4,4,3)),encoder_attention,encoder_norm,encoder_ff,encoder,target_embedded,decoder_self,decoder_norm,cross,decoder_ff,decoder,enc_weights,self_weights,cross_weights,head_outputs,concat,probabilities,predicted,future_mass,probability_sum:probabilities.reduce((a,b)=>a+b,0),memory_energy:cross.flat().reduce((s,v)=>s+Math.abs(v),0),position_energy:embedded.flat().reduce((s,v)=>s+Math.abs(v),0),time:0,phase:0};
}
export function advanceModel(s){s.time+=DT;s.phase=Math.floor((s.time+1e-8)/.8)%12;return s;}
export function run(params,steps){const s=createModel(params);for(let i=0;i<steps;i++)advanceModel(s);return s;}
