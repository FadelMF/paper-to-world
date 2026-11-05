// Euler reference model, teaching notes pp. 1–4. Units: ms, mV, nA, MΩ. Port of model.py.
export const DT = 0.1;
export function createModel(params = {}) {
  return { V: -65, time: 0, spikes: 0, refractory: 0, rate: 0, I: 0, tau: 20, ...params };
}
export function advanceModel(s) {
  s.time += DT;
  if (s.refractory > 0) { s.refractory = Math.max(0, s.refractory - DT); s.V = -65; }
  else { s.V += (-(s.V + 65) + 10 * s.I) / s.tau * DT; if (s.V >= -50) { s.spikes++; s.V = -65; s.refractory = 2; } }
  s.rate = s.spikes / (s.time / 1000);
  return s;
}
export function run(params, steps) {
  const s = createModel(params);
  for (let i = 0; i < steps; i++) advanceModel(s);
  return s;
}
export function measure(I, tau = 20, duration = 1000) { return run({ I, tau }, Math.round(duration / DT)); }
