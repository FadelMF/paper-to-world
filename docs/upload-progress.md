# Upload, progress and one selected view

One document produces **one** visualization, chosen by the Planner: `2d` or `3d`. Never generate a hybrid, two versions or a dimension switch. Prefer 2D when depth does not help explain the central idea.

## Progress page

`/build/{id}` is the progress page for PDF and arXiv input. Five steps advance:

1. Reading the paper
2. Finding the core ideas
3. Designing your world
4. Building & checking
5. Ready

The page polls `GET /api/runs/{id}` every 1.5 seconds and keeps the DOM nodes of unchanged chips, equations and activity lines. When step 5 is done and the artifacts exist, it opens the lesson after two seconds, or immediately on click.

`app/pipeline.py` writes `status.json` atomically. The fields are:

- `step`, `steps`, `headline`, `subline`;
- `activity`: up to five keyed lines, newest first;
- `waiting_hints`;
- `discovered`: title, authors, concepts, equations, modality, checks, parts, figures;
- `done`, `error`.

**How the text is made.**
- Lines come from fixed templates filled with real outputs: page count, title and concepts, figures read, equations proofread, the chosen view, parity cases, the scene's paper-based versus illustrative parts, the lesson count, the browser check and the Critic's review.
- No model writes progress text, and there are no percentages or timers.
- Source text that contains internal terms (`INTERNAL_WORDS`) is left out rather than rewritten.
- Technical details go only to `debug.log`. Learners see a fixed sentence, or the message of a `PublicError`.

## Queue, cancel and retry

- **Queue.** At most `PAPER_MAX_WORKERS` runs build at once. A queued run shows "Waiting for your turn" with its place, and starts automatically.
- **Cancel** (`POST /api/runs/{id}/cancel`). Stops the run's process group, including any running reference script, render check or browser. A queued run is taken out of the queue.
- **Try again** (`POST /api/runs/{id}/retry`). Starts a new run with the same PDF, or the original arXiv ID if the download never finished. It copies the earlier attempt's `checkpoints/` and figures, so stages that finished are not repeated. `?fresh=true` starts over.
- **Shutdown.** Stopping the server stops active workers and clears the queue.

## Example walkthrough

The public demo picker opens prepared examples directly. Tests can submit a prepared PDF and explicit example ID to the replay endpoint; a different PDF never silently receives example output.

The worker replays the example's stored stage answers (`DemoProvider`) through the real pipeline: the reference model really runs, and its numbers are really compared with `model.js`. Pacing is slowed for viewing. No model is called. The lesson then shows the example's label, if it has one.

## Verification

- `tests/test_build_progress.py`:
  - one modality and one view;
  - stage order and the details shown at each step;
  - no internal words in learner text;
  - private errors at every stage, and bounded repairs;
  - PDF, arXiv and retry routes, cancellation, the queue;
  - example walkthroughs for all three examples.
- `tests/browser_build_progress.py`: a real example upload in Chromium, through every step, automatic and manual handoff, cancelling a live worker, same-PDF retry, the stopped screen, layouts from 320 to 1440 px, and reduced motion.
