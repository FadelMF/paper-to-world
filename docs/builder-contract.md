# Writer and Builder → fixed lesson shell

The Writer returns one fenced `json` block, a 3–6 lesson array checked by `app.lesson_contract.validate_lessons`: every object ID it names must be a `scene.json` object and every control or preset parameter must be a model parameter. The Builder returns one fenced `javascript` block, the complete `world.js` ES module, checked by `validate_world`: the declared dimensionality, the direct exports below, an import from `./model.js`, and every scene object ID present as a string. No generated HTML shell and no legacy simulation-file support. How `scene.json` and `model.js` are made is in [visual-workflow.md](visual-workflow.md).

`static/lesson/index.html`, `style.css`, and `shell.js` serve both `/demo` and `/learn/{run_id}`. Incomplete runs redirect to `/build/{run_id}`. The progress page polls status; the lesson shell imports the run’s module only after successful completion. The homepage provides PDF/arXiv input, saved runs, and an explicit demo section.

## Lesson fields

Required fields: `id`, `title`, `intro`, `intro_links`, `equation`, `terms`, `predict`, `controls`, `challenge`, `figure_caption`, `scene_state`, `source`. See `static/demo/lessons.json` for four complete examples.

- `intro`: two or three plain-language strings. `intro_links` is a parallel array of scene object IDs, used during narration.
- `equation`: `latex` and `symbols` with `symbol`, `meaning`, `links_to`.
- `terms`: `term`, `definition`, `links_to`.
- `predict`: `question`, 2–3 string `options`, zero-based `answer_index`, `why`, positive integer `page`.
- `controls`: numeric `min`, `max`, positive `step`, numeric `default`, plus `symbol`, `label`, `units`. The default must match the parameter preset.
- `challenge`: `text` and `check_js`, a pure boolean expression over `state`. The shell evaluates it against `getState()` at most about seven times per second. Completion is recorded for the visit; Restart clears that lesson's progress.
- `learning` (required for mapped new lessons): `objective`, `action`, `observe`, `mechanism`, `focus`, `test_params` and `outcome_js`; the outcome must use a computed result, not only a control or clock.
- `scene_state`: `visible` (object IDs), `camera` ([x,y,z]), `params` (numeric parameter map). Every linked ID must be visible.
- `source`: `title`, positive integer `page`, and `kind` (`paper`, `background` or `simulation`). Only paper claims display page citations; simulation results are explicitly distinguished from paper results. Prediction explanations separately cite `predict.page`. The source PDF is served alongside the artifacts.

The first lesson establishes the whole system and its input/output path; a resting state is relevant only to models that actually have one. Subsequent lessons add one mechanism or equation each. The final lesson reproduces a passing required simulation target. Experiments outside the implemented model are explicitly identified as unmeasured source evidence; failed required targets block publication. General background is labeled; no fabricated paper results.

## World exports

The world imports `DT`, `createModel` and `advanceModel` from `./model.js` (the Porter's checked port) and never re-implements the model; one `advanceModel` call is one timestep.

All functions are direct named exports: `init(container)`, `setParams(obj)`, `setLesson(scene_state)`, `highlight(objectId)`, `getState()`, `play()`, `pause()`, `step()`, `onObjectClick(callback)`, `setAssembly(amount)`, `objectBounds()`.

`objectBounds()` returns `{objectId: {x, y, width, height}}` in CSS pixels relative to the container, for every scene object where it is drawn now; a signal with no geometry at the moment uses its anchor. `getState().time` is elapsed model time. Each scene object has one focusable tag element with `data-object="<id>"`. The render check relies on all three; see [visual-workflow.md](visual-workflow.md).

`setAssembly` accepts a finite number, clamps it to 0–1, and animates between saved component transforms. Zero is assembled; one is exploded. Invalid input leaves the target unchanged. Assemble/Explode buttons reflect this target, while `getState()` exposes `assembly` and `assemblyTarget`. Assembly is independent of scientific time and must work while paused, reverse in flight, restore exact home positions and respect reduced motion. New builds missing this named export fail bundle validation.

`init` creates rendering and observes size, without advancing time. `setLesson` sets preset and visible objects, resets the model, and transitions camera and opacity smoothly while retaining play/pause. `highlight(null)` clears highlighting. `onObjectClick` invokes the shell callback with the selected ID for pointer and keyboard activation. Clicking scrolls to the related left-panel term. `step` advances exactly one reference timestep only when paused. `getState` exposes parameters and live numeric model state for checks and readouts.

The shell sends `themechange` with `{dark}` and `explorechange` with `{enabled}` on the container. Read `--paper`, `--surface`, `--ink`, `--muted`, `--accent`, `--line`, and `--wash` from the container. Exploration must support pan/zoom for 2D or orbit controls for 3D, with accessible controls. Render meaningful objects as clickable shapes with focusable paper labels and live values nearby.

For 3D, the shell supplies a three.js 0.170.0 import map served from `static/vendor`: `three`, `three/addons/controls/OrbitControls.js` and `three/addons/environments/RoomEnvironment.js` are available, and `validate_world` rejects any other addon or URL import. The Builder uses physical/standard materials, differentiated roughness and metalness, RoomEnvironment reflections, ACES tone mapping, soft shadows, OrbitControls and raycast selection. Cutaways reveal internal structures. Native 2D Canvas draws detailed layered plates with material shading and device-pixel-ratio scaling. Both use readable theme-aware labels, an elegant museum specimen palette and accessible assembly controls. Anatomical detail must remain distinguishable from the validated scientific model; nonbiological subjects expose their actual constituent structures instead of invented anatomy.

Separate authored demos exercise the 2D and 3D paths. Each generated run selects exactly one modality and one matching view; hybrid/mixed plans are rejected. Only the selected renderer’s drawing instructions go into the Builder call. Its module declares `export const dimensionality = 2;` or `3;`, matching the plan. The lesson shell has no dimension switch. The two neuron examples share `static/lesson/specimen.js` and `neuron-parts.js`, also served at `/api/runs/{run_id}/lesson/…` so their relative imports work after a walkthrough build.

## Verification boundaries

The two neuron examples use authored teaching notes, not a published study; their numerical reference and browser model match across seven input, time-constant and duration combinations. The Transformer examples execute a small untrained encoder-decoder from arXiv:1706.03762, with six guided lessons and explicit coverage/outcome checks. Example tutor replies are stored and labelled.

The checks prove structure and numbers: the lesson contract, the world's exports and imports, Python/JavaScript parity, and what the render check measures in a browser. They do not prove that a live model writes good lessons or drawings; the Critic's review and the learner-facing labels address that, and docs/STATUS.md tracks it. Narration event order is tested with speech-API stubs; audible output depends on the device's voices.
