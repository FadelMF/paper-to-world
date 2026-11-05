# Paper-to-World teaching audit — 2026-11-03

The earlier Transformer examples passed execution checks while failing the learning task. The user could not locate an encoder or decoder, and lessons 1–5 repeated nearly the same attention scene. This audit captured all 18 existing lessons across the Transformer and neuron examples in both dimensions, then traced the generation prompts, contracts and browser tests.

## Findings from the captured flow

| Step | Captured behavior | Health before the fix | Change |
|---|---|---|---|
| 1. Open the paper example | The Transformer homepage promised a paper example, but the scene contained only Q/K/V attention | Critical scope mismatch | Both versions now show the encoder, decoder, memory connection and output feedback |
| 2. Move through lessons 1–5 | Same visible objects and camera, with small parameter changes | Poor progression | Six distinct numerical inspections with a persistent architecture map |
| 3. Change a control | Numeric weights changed without a clear explanation of input, transformation or output | Poor causal explanation | Each lesson states what to change, what to watch and why; named intermediate values are inspectable |
| 4. Complete a challenge | Some checks accepted a parameter setting alone | Misleading success signal | Outcomes must inspect computed results; the browser applies test inputs and waits for the actual consequence |
| 5. Explore neuron lessons | The checked integrate-and-fire model existed, but the visual emphasis favored anatomy; slow rendering could slow scientific time | Partly working, poorly explained | Live input/leak/derivative/threshold/count explanation; model progress decoupled from display-frame cap |
| 6. Inspect evidence | Parity and rendering were treated as adequate proof of paper fidelity | Inadequate acceptance criteria | Coverage map, explicit exclusions, observable-outcome tests and source-vs-demo evidence separation |

Before captures: [Transformer 2D](../artifacts/workflow-audit/before/attention2d-sheet.jpg), [Transformer 3D](../artifacts/workflow-audit/before/attention3d-sheet.jpg), [neuron 2D](../artifacts/workflow-audit/before/neuron2d-sheet.jpg), [neuron 3D](../artifacts/workflow-audit/before/neuron3d-sheet.jpg). Individual full-resolution screenshots and the observed lesson text/control inventory are in the same folder.

![Original five Transformer lessons repeated the same narrow scene](../artifacts/workflow-audit/before/attention2d-sheet.jpg)

## Why the workflow produced this

1. **Analysis began with the core equation.** The authored extraction selected attention before inventorying the paper. The Analyst prompt also asked for the core executable idea, without requiring a whole-paper learning map.
2. **Planning encouraged reduction without a coverage gate.** “Scope it down” and “one mechanism” allowed architecture and empirical evidence to disappear. Rendering modality was checked, topic coverage was not.
3. **The Builder lacked the full teaching intent.** It received scene states and controls rather than complete objectives, actions and observable outcomes. One static scene could satisfy every page.
4. **The tests checked execution rather than explanation.** A timer could advance while the computation stayed static. JavaScript parity only proved agreement with the authored Python, even when both omitted most of the paper. Challenge checks could echo parameters.
5. **Review did not compare the learning sequence with the paper outline.** A vision critic comparing crops is not a curriculum review. Offline authored runs did not use a live critic, and “prepared” replay skipped per-run browser checks.

## Workflow changes

- Live analysis must supply `learning_topics`. Long-paper merging retains the topic inventory.
- Planning maps every required topic to actual lesson IDs as `simulated` or `explained`; required topics cannot be silently excluded. Optional exclusions need reasons.
- After lesson creation, the pipeline writes `coverage.json` and verifies that mapped lessons exist and have learning instructions.
- Each new lesson has an objective, action, observation, causal explanation, focus objects, test inputs and a computed outcome expression. A parameter-only or clock-only outcome is rejected.
- The Builder receives the complete lessons and coverage/simplification map. Computational subjects are no longer forced into anatomy/explode presentation rules.
- The confined browser applies each lesson’s teaching inputs and waits for its computed outcome, in addition to existing playback, layout, controls and parity checks.
- Browser regression tests require six distinct Transformer inspection views, visible encoder/decoder connections and actual numerical outcomes. Neuron tests check equilibrium, threshold/reset and the real first-second counts.

Coverage gates validate the supplied map, not the truth of every sentence. Human/source review remains necessary; a model can still supply an incomplete topic inventory. Old extractions without a learning map remain explicitly marked as legacy. Live Analyst outputs require a map.

## Rebuilt examples

The Transformer now covers architecture, embeddings/positions, multi-head attention, residual/norm/feed-forward operations, decoder masking, encoder-decoder attention, output probabilities, autoregression, training schedule, regularization, computational comparisons, translation evidence, ablations, parsing and limitations. Some topics are demonstrated; costly training and empirical results are explained from the paper instead of fabricated.

The small untrained model computes one complete encoder/decoder layer with two heads. It does not claim trained translation ability or reproduction of the reported BLEU results. See [the detailed scope report](attention-examples.md).

The existing neuron sources are **authored demonstration notes**, not a published research paper. The checked model remains a leaky integrate-and-fire model. Organelles and pulse travel are explicitly illustrative. New text explains input current, membrane leak, time constant, threshold, reset, refractory interval and rate using the same measured state.

## Reproduce the retest

```bash
.venv/bin/python scripts/check_teaching_examples.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/run_browser_tests.py attention neuron_teaching
```

Reports are in `artifacts/teaching-pipeline-{2d,3d,attention2d,attention3d}/` and `artifacts/workflow-audit/`. Each pipeline run includes source extraction, sandboxed reference execution, JavaScript parity, coverage checks, lesson contracts, computed interaction outcomes, and desktop/phone renders. No model API is called by these authored example tests.

## Evidence limits

The audit tests curriculum coverage bookkeeping, numerical behavior, interaction, rendering and inspectable source references. Screenshots alone do not prove understanding or full accessibility compliance. A learner comprehension study and a live-provider evaluation on unseen papers remain unperformed. The local checks do not establish Meta authentication, quota or generated output quality.

## Retest results

- Historical regression run for the teaching change: 105 tests discovered, two environment-dependent tests skipped. See production-audit.md for the current full run.
- Transformer pipelines: both renderers passed topic coverage, Python/JavaScript parity in **11 parameter/step cases each**, all six computed teaching interactions and desktop/phone render checks.
- Neuron pipelines: both renderers passed coverage, **seven parity cases each**, the four computed interactions and desktop/phone render checks.
- The complete browser suite passed for both Transformer and neuron examples, including source figures, walkthrough routing and phone layout. Transformer lessons have six distinct numerical/evidence views. Neuron outcomes include 33 and 63 spikes in the same first-second measurement window.
- Ruff lint/format, Python type checks and JavaScript syntax checks passed.

After captures: [Transformer 2D](../artifacts/workflow-audit/after/attention2d-sheet.jpg), [Transformer 3D](../artifacts/workflow-audit/after/attention3d-sheet.jpg), [neuron 2D](../artifacts/workflow-audit/after/demo-sheet.jpg), [neuron 3D](../artifacts/workflow-audit/after/demo3d-sheet.jpg).

![Rebuilt Transformer sequence: architecture, positions, encoder, decoder, generation and evidence](../artifacts/workflow-audit/after/attention2d-sheet.jpg)

Final confirmation against the refreshed server also checked that the revised neuron challenge indicators agree with their learning outcomes: both 2D and 3D reached 33 and 63 spikes in the first-second window. The captures for those lessons were refreshed after that confirmation.

## Demo view standardization

Demo entry now opens viewers directly with Subject · 2D/3D titles. The author banner and replay/sample-upload controls were removed from the public example picker. Prepared replay URLs display the current example bundle, so old replay links do not combine old numerical artifacts with newly shared inspector code. Live user-paper runs continue using their own artifacts. Desktop viewers now stay within one viewport with independently scrolling reading and detail panels; phone viewers stack and use document scrolling. All component matrix rows remain reachable on expansion. Neuron inspection now docks inside the right simulation panel, beside the model when wide and below it when narrow, with equally sized Focus component, Reset view and Close actions. Selection, focus and reset preserve the panel and document scroll. The Transformer renderer displays full token-feature cells and exposes Q/K/V projection arrays.
