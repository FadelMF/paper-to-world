# Shared white and blue learning workspace

The current specimen direction is an elegant museum exhibit. Anatomical surfaces use ivory ceramic, muted blue resin and satin brass with environment reflections and cutaway detail. Warm colors belong to the specimen; navigation retains the shared white/blue theme. Explode and assemble motion reveals construction and must remain independent of scientific time. ENERGY 2 / RHYTHM 2 / MOTION 3 for the specimen.

The user's replacement direction takes precedence over the previous cream/ochre editorial theme and the separate blue/green upload theme. All surfaces share `static/ui/app.css` and `app.js`.

- White is the default canvas; pale blue-grey separates the interactive world from reading. Meta/Facebook-inspired blue is the single action and selection accent. Red is reserved for errors. No paper grain, warm palette, or unrelated progress gradient.
- Inter is the interface and heading face. KaTeX keeps mathematical notation. Controls use a consistent 44 px minimum target, 10 px radius, clear focus, and visible labels for main actions.
- One persistent header returns to Start and Your worlds. The home workspace offers Examples and Your paper. Selected examples are previewed one at a time; the main action opens that example and a secondary action follows its PDF through the build.
- Live PDF/arXiv input shares that entry, progress screen, and lesson shell. Availability is reported honestly. No generated document gets two visualizations.
- The lesson uses a connected reading/world pair, an explicit lesson path, a readable control dock, and focus exploration. On narrow screens the live world stays above the independently scrolling lesson so changing a control remains observable.
- Theme preference, buttons, icons, status, empty/error/loading states, and navigation belong to the same system. White is the default; the optional shared night mode uses the same accent and structure everywhere.
- Motion communicates a selected example, a completed step, a lesson transition, or a highlighted scientific object. Reduced motion preserves the content and controls.

Verification targets: entry, live input, the four prepared previews, both renderers (2D Canvas, 3D WebGL), progress/error states, source/question controls, and mobile. Local server remains available for SSH; no public tunnel.


After the teaching audit, Transformer examples use a persistent connected encoder/decoder map with a distinct numerical inspection per lesson. Generated output is outside the encoder stack, with a feedback link to shifted decoder inputs. Objectives and Try/Watch/Why instructions appear before equations. Neuron diagrams are paired with an actual-state causal explanation. Phone layouts give these diagrams room and scroll the reading rather than compressing labels into an unreadable fixed panel. See docs/workflow-audit.md.

The 2026-11-04 refinement separates renderers clearly: flat connected map for 2D; perspective encoder/decoder stacks with feature bars and orbit/pan/reset/spacing controls for 3D. 3D labels live in a component picker, leaving geometry unobstructed. Teaching actions and controls appear together before equations. Binary settings are named dropdowns; wide continuous sliders show units and baseline gain.

The neuron state panel separates input current, membrane voltage and first-second spike count into three aligned columns. Calculation terms and model scope live in a native expandable section. Values update in place so keyboard focus and the expanded state survive simulation frames.

All live-result panels use labeled value groups and expandable technical sections. Transformer vectors, intermediate computations, attention matrices, model setup and source evidence no longer appear as long inline paragraphs. Dropdown triggers and option lists use the shared in-page component in static/ui/dropdown.js, with keyboard navigation, focus, theme colors and viewport placement. Native select elements remain hidden backing controls for values/events.

Desktop world viewers stay within one viewport: the reading column scrolls independently and the simulation remains visible beside it. The right panel and long computed-detail sections contain their own overflow; neither column may make the document scroll or leave a blank opposite column. Phone viewers stack the world above the reading and use document scrolling. All demo entry labels follow Subject · 2D/3D, with no generation walkthrough or author banner. Neuron Anatomy is docked inside the right simulation panel. Wide specimen areas place it beside the model; narrow areas place it below the model. It replaces the summary metrics while open and restores them on Close. The selector, live-value badge and equal-size Focus component / Reset view / Close actions remain visible; only the description scrolls. Opening, selecting, focusing, resetting and closing must preserve page scroll; simulation updates must keep the inspector open. Information disclosures never force page scrolling. Transformer 3D layers show full token-by-feature tensors; inspection provides all token rows and attention Q/K/V projections.
