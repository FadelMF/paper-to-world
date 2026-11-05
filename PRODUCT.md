# Paper-to-World
<!-- impeccable:product-schema 1 -->

## Platform
web

## Product Purpose
Help a learner understand a scientific paper by reading connected lessons, predicting outcomes, changing inputs, and exploring a running visualization.

## Operating Context
The user previews this application from a Mac through an SSH tunnel to the local server. Keep the server on 127.0.0.1:8000. Do not start Cloudflare. Prepared neuron examples and live PDF/arXiv generation must start from one shared entry page.

## Capabilities and Constraints
- Existing FastAPI backend and plain HTML/CSS/JavaScript; no framework or frontend build step.
- Each new document produces exactly one selected 2D or 3D world. No hybrid generation or output dimension switch.
- Prepared examples include neuron teaching notes and 2D/3D encoder-decoder Transformer lessons from Vaswani et al. (arXiv:1706.03762). Examples are authored teaching material validated through the pipeline.
- The pipeline's stages run in a fixed order with a check between each (docs/visual-workflow.md); the progress page shows five learner-facing steps. Progress uses factual templates, with no extra narration request.
- Live generation requires configured provider credentials, Node.js and kernel isolation (Landlock); the home page states which is missing. Browser narration uses the device's speech service.
- Preserve predictions, reveals, sliders, challenges, pause/step, narration, object links, focus exploration, source references, and questions about the paper.

## Brand Commitments
User explicitly requests a white theme with Meta/Facebook-style blue accents, one design baseline across entry/upload/progress/2D/3D, and a more interactive, immersive, friendly experience. Product identity remains Paper-to-World.

## Evidence on Hand
Authored example PDFs, attention-paper stage answers, lessons, Python reference implementations, 2D Canvas and WebGL renderers, integration tests and browser verification live in this repository. No claim of tested live generation without credentials (docs/STATUS.md).

## Teaching quality gates
Live extraction inventories paper learning topics; plans map them to simulated or source-explained lessons. Required topics cannot be silently excluded. New lessons specify an objective, input action, observable computed outcome and causal explanation. Automated browser checks execute the teaching interaction. These gates complement numerical parity; they do not replace source review or a learner comprehension study.
