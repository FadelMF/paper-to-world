# Production audit — 2026-11-04

Scope: application source, prepared neuron/Transformer content, upload/arXiv transport, generation/publication gates, process lifecycle, shared frontend, dependency inventory, repository hygiene, tests and operational documentation.

This file is a historical audit of the pre-release implementation. Findings marked unresolved below were the state at that audit, not the current source. See [public release review](public-release-review.md) for implemented isolation, ownership, budgets and current verification, and [deployment](deployment.md) for operation. Historical test totals remain with their original scope.

## Historical deployment assessment (before the release implementation)

The supported deployment is a **private, single-server workspace for trusted users**, behind an SSH tunnel or trusted HTTPS reverse proxy. This is not yet a public multi-user service. All holders of the shared token can access every run, and generated JavaScript executes in the application origin. A CSP or a string-based source check does not isolate arbitrary generated JavaScript from same-origin APIs. A trusted operator can still upload an untrusted paper; token access and backend confinement do not provide browser isolation for the resulting generated code. Production generation from untrusted papers requires a sandboxed execution origin. Public use requires a separate sandboxed execution origin and per-user authorization before exposing generation to untrusted users.

The Meta Responses adapter has SDK-over-HTTP tests, but no real provider credentials were available. Authentication, model availability, quota, image compatibility, generation quality and real cost are **unverified**. Config readiness is a local prerequisite check, not a provider connectivity test.

## Findings and fixes

| Finding | Change | Verification |
|---|---|---|
| Generated JavaScript shares the application origin | **Unresolved production boundary:** isolate generated code in a sandboxed execution origin before accepting untrusted papers in production. Shared-token access is insufficient. | Source inspection; current CSP/render checks do not establish browser isolation |
| Required numerical checks could fail while the pipeline still published a ready world | Every planned target now requires exactly one passing result and a finite measured metric; numeric expectations/tolerances are checked directly where available. Source-only benchmarks remain distinct. Rejected model/derived checkpoints are invalidated so retries regenerate them. | Publication regression tests and example pipelines |
| Unresolved major visual criticism could be retained at publication | Stop publication after exhausted or invalid major corrections. Minor criticism remains advisory. | Visual publication regression and scripted vision workflow |
| Canceling a worker could leave its separately grouped model/browser child alive | SIGTERM unwinds the worker; sandbox cleanup kills the child process group in `finally`, including interrupts. Workers monitor the original server parent and terminate after abrupt server exit as well. | Cancellation regression, sandbox tests, browser cancel/retry |
| Server restarts could strand unfinished builds | Production startup marks interrupted runs stopped and retryable. | Recovery regression |
| In-memory queue could be shared accidentally across server processes | Production runs-directory lock rejects a second owner; production launcher uses one Uvicorn worker. Spawn failures mark the affected build stopped. | Ownership regression and startup checks |
| Oversized uploads were fully read before validation, and downloads were unbounded | Bound ASGI request streams before multipart parsing, bound UploadFile reads, and bound arXiv downloads. Validate arXiv IDs in the downloader too. | Declared/streamed request, upload and downloader regressions |
| Arbitrary run files and escaping symlinks could be served | Explicit learner-artifact allowlist and resolved-path containment; internal logs/source/usage files stay server-side. | Artifact and symlink regression |
| Tutor accepted unbounded or empty input and unfinished runs | Trim and bound questions to 2,000 characters; reject unfinished runs before provider calls. | Tutor input/state regressions |
| Cross-origin form submissions could start work on a local server | Reject explicit foreign origins for mutating requests. | Cross-origin regression |
| Stale cookie could override a valid Bearer header | Explicit query token, then Bearer credential, then cookie; Bearer scheme is case insensitive. | Auth regression |
| Private API responses could be cached and file types were not protected from sniffing | `no-store` for API/authenticated responses; `nosniff`, no-referrer and anti-framing headers. | Response/header regression and browser navigation |
| Production had no required safe configuration | `scripts/serve.sh` enables production mode; startup requires a sufficiently long token, positive rate limit and kernel confinement. | Configuration rejection tests |
| Node 18 was documented although the code uses `--permission`; missing Chromium was not reported by readiness | Check installed Node permission support and Chromium; document Node 22.13+. Probe browser installation outside the HTTP event loop. | Async upload/prerequisite regression |
| Installed pypdf 6.21.2 had known advisories | Upgrade to 6.21.4 and require at least that version. | Python dependency audit |
| Vendored KaTeX 0.16.11 had known advisories | Upgrade JS, CSS, fonts and license together to 0.19.1; retain `trust:false`. | npm audit and equation/browser tests |
| Wheel installs omitted frontend assets; implicit dotenv discovery depended on the source tree | Bundle the static asset package, exclude bytecode/cache files, and load `.env` explicitly from the working directory. | Installed-wheel smoke test outside the checkout |
| Dependency installation was not reproducible | Add `uv.lock`, development dependency group and locked verification/launcher commands. | `uv lock --check`, installed dependency check |
| Neuron metric markup failed the definition-list accessibility rule | Keep the measurement-window annotation inside its metric definition. | All-page axe audit |
| Source-text filter removed valid scientific terms such as tokens and agent reasoning | Preserve source text; test operational copy separately from scientific titles/concepts. | Progress source-text regression |
| The fixed control dock could cover lesson-navigation targets during browser focus/scroll | Reserve dock clearance in the document scroll area and interactive scroll margins. | Mobile navigation/dock-clearance regression and unified browser flow |
| Repeated Anatomy CSS overrides retained obsolete positioning rules | Consolidate inspector rules and explicit close semantics. The subsequent Anatomy refinement docks inspection inside the right panel, beside or below the model, with a scrollable description and always-visible controls. | Scroll stability and inspector controls tests |
| Browser challenge test used an obsolete 1.6 nA input for the 2 nA/33-spike lesson | Use the actual lesson target and allow software-rendered first-second simulation to complete. | Neuron 3D browser test |
| Documentation asserted current zero duplication / clean audits based on old runs | Replace current status with dated evidence and limitations; update Node/KaTeX versions, scrolling behavior, publication rules and provider configuration. | Documentation review |
| Old source ZIP and incomplete ignore rules could confuse packaging or expose env variants | Remove the superseded initial ZIP; ignore private env variants, caches and root build outputs while retaining `.env.example` and the real `static/build` source. | Source scan and tree review |

## Dependency sources

- [pypdf page-tree memory advisory, fixed in 6.21.4](https://github.com/advisories/GHSA-cggf-277g-3q54).
- [pypdf xref infinite-loop advisory, fixed in 6.21.4](https://github.com/advisories/GHSA-5849-834g-hvw5).
- [KaTeX attribute-name advisory](https://github.com/KaTeX/KaTeX/security/advisories/GHSA-cg87-wmx4-v546).
- [KaTeX inherited trust-setting advisory](https://github.com/KaTeX/KaTeX/security/advisories/GHSA-238p-pmpm-9mq7).
- [Node permission model documentation](https://nodejs.org/download/release/v22.17.0/docs/api/permissions.html).

`static/vendor/versions.json` records JS package versions and SHA-256 checksums for the main vendored runtime files. Third-party license files remain next to the assets.

## Reproduce verification

```bash
uv sync --locked
uv run --locked python -m playwright install chromium
scripts/check.sh --browser
uv run --locked python scripts/check_teaching_examples.py
uv run --locked pip-audit
uv run --locked python scripts/audit_vendors.py
```

Vendor audit: create a temporary npm project with the exact dependencies from `static/vendor/versions.json`, generate its lockfile with `npm install --package-lock-only --ignore-scripts`, then run `npm audit`. No npm runtime or frontend build is required by the application.

| Final verification | Result | Evidence |
|---|---|---|
| Ruff lint / format | Pass; 54 Python files formatted | `scripts/check.sh` configuration |
| Pyright | 0 errors / warnings | `artifacts/types-verified.log` |
| JavaScript syntax | All application modules pass Node syntax checks | `artifacts/production-verification.json` |
| Unit/integration regression | 118 discovered: 116 passed, 2 input-dependent skips | `artifacts/tests-verified.log` |
| Latest security/publication regressions | 14 passed, including rejected-checkpoint retry and worker-parent lifetime | `artifacts/security-verified.log` |
| Browser scripts | All 14 pass using each script's final rerun | `artifacts/production-verification.json` and referenced logs |
| Accessibility | 52 views; 0 axe WCAG A/AA violations | `artifacts/production-final-browser.log` |
| Authored example pipelines | All four pass: model, parity, coverage/outcomes, confined desktop/phone renders | `artifacts/production-example-pipelines.log` |
| Python dependency audit | 0 known vulnerabilities in the scanned environment | `artifacts/dependency-audit-final.json` |
| Vendored npm dependency audit | 0 known vulnerabilities | `artifacts/vendor-audit-verified.log` |
| Production startup | Authenticated pages/config work; second owner rejected | `artifacts/production-startup-smoke.log` |
| Distribution | Wheel/SDist build; assets and working-directory dotenv verified outside checkout | `artifacts/package-smoke.log` |
| Source hygiene | No recognizable credentials in the heuristic source scan; no high-confidence unused names after excluding required callback arguments | `artifacts/secret-scan.json`, `artifacts/production-dead-code.log` |

The two skipped full-suite tests require real PDFs (`REAL_PDF_DIR`) and live credentials (`LIVE_LLM`). The full unit run predates the final two focused regression additions; the separate 14-test security run covers those additions. The browser summary combines the full sweep and successful targeted reruns after correcting obsolete UI assumptions, waiting for real asynchronous outcomes, and fixing dock clearance. It does not hide failed baseline runs.

## Remaining release decisions and limits

- No project license has been chosen. The owner must choose one before distributing the project's own code.
- There is no project Git repository or CI setup; these were not created as part of this audit. Local reproducible check scripts are available.
- Rate limits and the queue are per process; process restarts reset rate history. Distributed/multi-worker deployment is unsupported.
- Kernel confinement needs Linux 6.7+ on x86_64. Chromium's own sandbox is unavailable on this host; generated render checks use Landlock/seccomp. The `guard` backend is development only.
- File-size/request limits do not prove bounded CPU or memory consumption for every malformed PDF. Run the service as an unprivileged account under OS/container resource limits when accepting outside documents.
- Numerical parity means that the two implementations agree; coverage, source quotes, browser outcomes and visual review still do not prove scientific fidelity or learner comprehension.
- Automated accessibility does not replace screen-reader and human usability testing.
- No audit can guarantee that all bugs have been eliminated. The evidence below states what actually ran.

## Local handoff

The local server was restarted on 127.0.0.1:8000 after verification. Five entry/example routes and the new cache/security headers passed a smoke check. Live generation remains unavailable until real provider credentials are configured. See `artifacts/local-server-verification.json`.

## Workspace layout correction

Desktop viewers retain a single-viewport workspace across neuron and Transformer 2D/3D examples. Reading scrolls independently; the simulation frame stays beside it and long right-hand inspections remain reachable inside their panel. Phone viewers retain their stacked layout. The follow-up regression is `tests/browser_fixed_workspace.py`; this supersedes the earlier natural-document-scroll behavior on desktop. The fixed workspace, information panels, scroll stability and standard-demo browser scripts all passed after this correction. Evidence: `artifacts/fixed-workspace-verification.log` and `artifacts/fixed-workspace-details.log`.

## Anatomy docking refinement

Anatomy now stays inside the right simulation panel, beside the model for wide specimen areas and below it for narrow areas. A live-value badge sits beside the field label; descriptions scroll separately from the selector and actions. Closing inspection restores the summary metrics and preserves an explicitly focused 3D camera target. The learner shell and home preview share this behavior. `browser_anatomy_docked.py` checks panel/model bounds, visible controls, keyboard behavior, focus preservation and summary restoration across desktop and phone layouts.
