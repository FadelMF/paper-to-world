# Transformer examples: architecture and verification

The examples now cover the complete encoder-to-decoder path, rather than only the attention equation. Source: [Attention Is All You Need](https://arxiv.org/abs/1706.03762), Vaswani et al. Citations use the included 15-page PDF.

| Lesson | What changes on screen | Paper scope |
|---|---|---|
| 1. Architecture | Changing the source changes encoder memory, carried into decoder cross-attention | §3, p.3, Figure 1 |
| 2. Positions | Turning positional encoding off changes the vectors entering both stacks | §§3.4–3.5, pp.5–6 |
| 3. Encoder | Compare parallel heads, concatenation, projection, add/norm and feed-forward output | §§3.1–3.3, pp.3–5 |
| 4. Decoder | Compare masked self-attention and cross-attention; remove future access and cut encoder memory | §§3.1, 3.2.3, pp.3–5 |
| 5. Generation | The predicted token is appended to the next decoder prefix | §§3, 3.4, pp.3–5 |
| 6. Evidence | Evaluate the warmup/decay schedule; inspect source benchmarks and limits separately | §§4–6, pp.6–9 |

Both versions use a small deterministic, **untrained** Transformer: one layer per stack, four model dimensions, two heads and an eight-unit feed-forward hidden layer. They compute Q/K/V projections, scaled dot-product attention, head concatenation/output projection, residual addition, layer normalization, feed-forward layers, positional encoding, decoder masking, encoder-decoder attention and greedy autoregression. The paper’s base configuration is six layers per stack, 512 model dimensions and eight heads. The small model illustrates the architecture; it is not a trained translation model.

Optimization and regularization, complexity comparisons, translation results, ablations, parsing and appendix attention visualizations are addressed as source evidence. The demo evaluates the paper’s learning-rate equation with its stated configuration; it does not train or reproduce BLEU/parsing benchmarks. Stage answers are authored locally, as requested. Live-provider prompt quality remains a separate evaluation.

Reproduce all four examples with:

```bash
.venv/bin/python scripts/check_teaching_examples.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tests/run_browser_tests.py attention neuron_teaching
```

Read [the workflow audit](workflow-audit.md) for the failures that allowed the earlier attention-only example and the new coverage/outcome gates.

## Control and 3D refinement — 2026-11-04

The 3D example uses a perspective camera and spatially separated encoder/decoder stacks, with real feature bars, orbit/pan, reset and layer-spacing controls. The component picker stays beside the geometry on desktop and below it on phones. The 2D version keeps the flat architecture map. Numeric details stay in the selected inspection panel.

Binary settings use named dropdowns. Continuous exploration ranges are now:

| Control | Range | Baseline |
|---|---|---|
| Embedding strength | 10–300% | 100% |
| Position signal strength | 0–300% | 100% |
| Attention sharpness | 10–400% | 100% |
| Encoder memory contribution | 0–200% | 100% |
| Generated sequence length | 1–12 tokens | 3 tokens |
| Schedule step | 1–32,000 | 4,000 |

The gains are teaching interventions: 100% retains the baseline model. They are computed in both the Python reference and the JavaScript model; they are not paper-reported experimental settings. Endpoint tests verify that each gain changes the relevant computed arrays, with ten additional Python/JavaScript parity cases including 12-token generation.

The neuron controls were widened to 0–10 nA and 5–100 ms. Both neuron ports still match their references at the new parameter edges (seven cases per renderer).

Verification: both Transformer full pipelines and the six-lesson browser suite passed, including camera rotation, spacing, source figures, walkthrough selection and desktop/phone layouts. Three attention tests, three teaching-contract tests and fourteen progress/entry regression tests passed. See `artifacts/transformer-refinement-*.log`.

## Complete component inspection

The 3D layer cells now represent every token/feature value, not just the first row. Inspectors display the full matrix; encoder attention additionally exposes Q/K/V projections from the numerical model. Prepared demos open directly, with uniform Subject · 2D/3D labels. The removed walkthrough remains a developer/test replay endpoint, not a demo-page action. Desktop viewers keep the simulation beside an independently scrolling reading column. Long inspections scroll inside the right panel; phones stack the world and reading. Wide matrices scroll horizontally when needed.
