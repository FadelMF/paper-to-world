# API readiness — updated 2026-11-04

Current startup uses Meta endpoint/model/protocol defaults: `LLM_API_KEY` alone is sufficient configuration. See [deployment.md](deployment.md) for the current launcher, isolation, accounts and usage limits. The original integration findings below retain their historical scope.

The app has a real generation pipeline. Prepared examples deliberately read stored artifacts and canned tutor answers; they remain examples after a key is configured. Uploading through **Use your paper** invokes the configured model. A failed live build does not silently switch to a demo.

The supplied Meta tutorial uses `/v1/responses`. The original client used `/v1/chat/completions`, so changing only its key and URL would not reproduce the tutorial. The client now supports `LLM_API=responses`; Chat Completions remains the default for existing configurations.

For Meta, create `.env` in the project root with:

```dotenv
LLM_API=responses
LLM_BASE_URL=https://api.meta.ai/v1
LLM_API_KEY=your-meta-key
LLM_MODEL=muse-wonder-1.0
```

Restart the server after changing configuration. The standalone `scripts/meta_example.py` preserves the tutorial's `MODEL_API_KEY` name; the app uses `LLM_API_KEY` instead. Run the standalone example with `.venv/bin/python scripts/meta_example.py`.

Only set `VISION_MODEL` to a model confirmed by your provider to accept images. Vision inherits the text endpoint, key and protocol; `VISION_BASE_URL`, `VISION_API_KEY` and `VISION_API` can override them. Without vision, figure reading, equation proofreading and visual criticism are skipped; scanned papers require vision.

## Verification limits

- No real API credentials were present during this audit. Provider authentication, quota, model availability and real generation quality have not been verified.
- The SDK Responses adapter is tested against a local HTTP server, including text, images, token usage, incomplete/failed responses and empty output. This does not establish Meta's support for image inputs, system messages or `max_output_tokens` (which the app adds to bound output).
- `/api/config` checks configuration and execution prerequisites, not API authentication or model connectivity.
- Required planned simulation targets must now pass with finite measured metrics before publication. Unresolved major visual criticism blocks publication. Source-only benchmarks may be explicitly unmeasured. Numerical parity establishes that JavaScript matches generated Python, not that the paper was faithfully reproduced.
- The full browser workflow uses scripted model replies. It exercises real HTTP calls, workers, model execution and rendering, but not live-provider model behavior.

After adding credentials, run `.venv/bin/python scripts/live_run.py /path/to/paper.pdf` for a persistent full-pipeline test. Inspect its `usage.json`, validation results, parity report, render report and any `critique.json`, rather than relying only on the ready status.

## Historical checks (2026-11-03)

Current verification and deployment limits are recorded in [production-audit.md](production-audit.md).


The baseline suite passed: 99 tests, with two environment-dependent tests skipped. The browser upload-to-world test passed for 2D and 3D with scripted HTTP model responses and no browser errors. The new Responses adapter passed three SDK-over-HTTP tests. Ruff lint/format and Pyright checks passed. These checks are local and do not make requests to Meta.
