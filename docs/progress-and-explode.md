# Progress feed and the neuron examples' Explode

The progress page uses `--page-pad`, the same horizontal container as the header, Home and lessons. Its 40/60 grid fills the viewport. The active step owns the headline, subline, at most five keyed activities, and waiting hint. Completed steps collapse. Below 900 px the columns stack within the viewport; each column can scroll independently. Discoveries retain their arrival animations and have an explicit empty state.

`Progress.add(key, text, done)` writes stable action identities to `status.json`. Reading, planning, comparison and lesson-building details replace their corresponding placeholders. Starting a step clears the preceding step’s activity. The browser updates the same keyed DOM node when a more specific line arrives.

This applies to the two neuron examples (`/demo`, `/demo/3d`). The Transformer examples and generated worlds draw their own Assemble/Explode control from the same CSS.

`static/lesson/neuron-parts.js` defines the seven teaching parts once: IDs, names, descriptions, lesson links and live values. Both prepared worlds consume it. The 3D inspector extends that inventory with its existing organelle detail. Rebuilt examples load the shared modules through `/api/runs/{id}/lesson/…`.

2D Explode arranges the parts in teaching order, with numbered labels, a faint dashed direction arrow and thin leaders. The geometry interpolates over 400 ms independently of the model clock. Labels occupy alternating lanes outside the complete shape bounds, with extra lanes when needed. The inspector occupies the lower region on desktop; on phones the diagram scrolls inside its world panel and the inspector opens over the viewport. Both part picking and label buttons select the same inspector and matching lesson term. Missing teaching terms are added from the shared inventory when the prepared lesson loads.

The scientific integration, threshold, reset, reference outputs and measurement window are unchanged. Six myelin segments and three terminals are schematic. They add no parameters or model behavior.

Design direction: the existing white/blue learning workspace, Inter typography, and ceramic 3D specimen. ENERGY 2 / RHYTHM 2 / MOTION 3. The progress split separates ongoing activity from discoveries; the numbered path and leaders explain part order and identity. Blue denotes current activity or selection. Pulse, entry and assembly motion convey actual state, with reduced-motion support. No decorative assets, metrics or testimonials were introduced.

Verification:

```sh
python3 tests/browser_progress_explode.py   # Explode matrix: 1440×900 and 1920×1080, light and dark
python3 tests/browser_build_progress.py     # progress page, cancel, retry
```

The matrix test starts an isolated local server and uses real sample-upload workers. It checks 1440×900 and 1920×1080 in light and dark themes, captures screenshots in `artifacts/` (not versioned), and writes individual results to `artifacts/progress-explode-checks.json`. It measures label rectangles against conservative bounds enclosing the drawn Canvas paths, tests every part and label, checks linked terms, live inspection values, motion and exact reassembly, and compares all seven IDs, names and values against 3D. Additional checks cover keyed DOM replacement, 390/899/900 px progress layouts, overflowing discoveries and reduced motion. The regression script covers cancellation, retry and manual/automatic handoff.
