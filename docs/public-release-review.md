# Release implementation · 2026-11-05

The code-level release work now includes browser isolation, private guest workspaces, optional username/password accounts, persistent limits and a single-host deployment configuration. **Real Meta output is not verified without the owner's key.** Domain/TLS activation, systemd installation, capacity testing and off-host backup scheduling are host-specific actions, not already-deployed services. Follow [deployment.md](deployment.md).

## Implemented boundaries

| Area | Implementation | Verification |
|---|---|---|
| Generated browser code | Opaque `allow-scripts` iframe with an independent HTTP sandbox CSP; no network, frames, workers or forms; generated challenges stay in the iframe. Parent has a bounded simulation-only MessageChannel and no arbitrary fetch bridge. | Real 2D/3D render and hostile parent DOM, cookie, storage, navigation and API probes |
| Ownership | Random HttpOnly session credentials, stored as hashes; per-run ownership enforced on all read/mutation routes in production; optional username/password accounts preserve ownership across devices. Existing unowned runs are not claimed. | Two independent clients; restoration of an existing session; denial on list/status/artifact/library/page/cancel/retry/tutor routes |
| Request and usage limits | SQLite-backed per-session/IP limits; atomic conservative reservations before provider requests; daily session/global and per-build limits; SDK automatic retries disabled. | Concurrent reservations, persistence across connections, exhausted budgets never open a provider connection |
| Process limits | Worker CPU/wall/address-space limits, existing Python/Node confinement, whole-service resident-memory/CPU/task limits in systemd template. | Worker-driven HTTP fixture pipeline; resource template review. Service cgroup requires installing the unit. |
| Startup | Meta endpoint/model/protocol defaults; either LLM_API_KEY or MODEL_API_KEY; `scripts/start.sh` installs locked dependencies/browser and starts private-session production mode. | Key-only configuration test; no real provider request |
| Operations | HTTPS proxy template, health endpoint, offline SQLite/artifact backup, retention defaults, independent local Git repository and GitHub Actions workflow. | Build/check scripts and backup tests; remote CI and public host installation are not executed here |

Private guest sessions avoid mandatory signup. Optional username/password accounts preserve the current workspace across browsers; passwords are salted scrypt hashes, login rotates credentials, and logout revokes them. Clearing guest cookies loses access. Registered users can sign in again; no email/password-reset service is included. Seven-day run retention is the production default, while session credentials expire after 30 days. An optional shared entry gate never bypasses ownership.

Reservations use conservative input bytes, maximum output tokens, image allowances and protocol overhead. They are not actual provider billing or a guaranteed dollar cap; configure the provider account's spending ceiling too. Failure reservations are not refunded. Runtime data stays outside source control and package outputs.

## AI behavior

Normal uploads invoke the actual configured adapter. Prepared example routes and walkthroughs intentionally use stored artifacts and tutor answers. Provider errors never substitute demo content. Without VISION_MODEL, image interpretation and screenshot critique are skipped; numerical/contract/browser checks still run. No claim is made that text parity or an LLM validator proves scientific fidelity. The real-key acceptance test should include neuron and Transformer papers, checking failed stages, latency, usage and the final teaching content.

## Evidence

- `artifacts/release-isolation.log`: actual isolated 2D/3D rendering and hostile browser probes.
- `artifacts/release-boundaries.log`: 38 ownership, budget, production, transport and queue regressions passed at the initial boundary check.
- `artifacts/release-live-path-verified.log`: intermediate browser run; superseded by the final Responses-protocol pipeline log below. All provider fixtures are local, not Meta.
- `artifacts/release-final-check.log`: final full static/unit/integration checks.
- `artifacts/release-accounts.log`: 29 final account/ownership/production/transport checks passed.
- `artifacts/release-responses-pipeline.log`: end-to-end Responses-protocol fixture pipeline for text and vision.
- `artifacts/release-browser.log`: final targeted prepared-example layout and browser isolation checks.

Earlier audit evidence is retained in [production-audit.md](production-audit.md) with its historical scope. Earlier live-path attempts exposed a screenshot timeout and a loading-state race. The final rerun is recorded separately. The initial full check shell was edited while its unit subprocess was running: all 129 unit tests completed (127 passed, 2 skipped), but the shell then read an outdated file offset and failed. The corrected script is checked again in the final verification; that wrapper failure is not counted as a clean command pass.


## Final verification

- Final full check: 134 tests, 132 passed and two opt-in real-input/provider skips; lint, formatting, types and 24 JavaScript syntax checks passed (`release-final-check.log`).
- Final hardening after that sweep: 37 account/ownership/production/Responses/sandbox tests passed, including kernel-level rejection of status/world overwrites (`release-final-security.log`).
- Four browser scripts passed: accounts, Anatomy docking, fixed workspace across four prepared examples, and hostile-code isolation (`release-browser.log`). The account browser flow was repeated successfully after strengthening password hashing (`release-final-account-browser.log`).
- End-to-end upload → worker → HTTP Responses text and vision fixture → source/number/render/critique checks → working 2D and 3D learner frames passed with no browser errors (`release-responses-pipeline.log`). This is not a real Meta request.
- Environment compatibility tests passed after creating the blank local `.env`; no credentials were inserted.

- Actual `scripts/start.sh` production startup passed without a provider key: health, session cookies, accounts and sandbox headers (`release-startup.log`). The temporary smoke server was stopped.
- Final wheel bytes match the delivered backend/frame/account code; source archive includes startup, deployment and CI files and excludes private state. The prior long-running development server was stopped so the user can launch the new version on port 8000.
