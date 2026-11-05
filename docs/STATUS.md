# Project status

Updated 2026-11-05. Current audit, exact verification results and remaining deployment limits live in [public-release-review.md](public-release-review.md) and [deployment.md](deployment.md). Historical implementation checks in other documents describe their dated changes, not a guarantee about the current tree.

## Implemented

- PDF/arXiv reading, optional vision stages, scientific model generation, Python/JavaScript parity, source evidence, lesson coverage, numerical publication gates and browser/render checks.
- Four authored examples: neuron 2D/3D and Transformer 2D/3D, with structured numerical inspectors and custom dropdowns.
- Worker queue, cancellation, retries, retention, private guest-session ownership, persistent request/token limits, opaque browser isolation and production startup checks.
- Vendored frontend libraries and a Python lockfile; dependencies are scanned during the production audit.
- Lint, formatting, type checking, unit/integration tests and browser suites. Use `scripts/check.sh --browser` from a locked development install.

## Still requires external verification or owner decisions

- Real Meta authentication, quota, model compatibility, generation quality and cost require locally configured credentials. Scripted HTTP tests do not establish those results.
- Production supports private guest sessions and optional username/password accounts. Guests lose access after cookie loss; registered users can sign in across devices. No email password-reset service is configured. Domain/TLS activation, service installation, capacity testing and off-host backups remain host-specific deployment tasks.
- Distributed queues, shared rate limiting and multiple Uvicorn workers are unsupported. Production mode enforces one owner of the runs directory.
- The project has no license for its own code; the owner must choose one before distribution. Third-party licenses are retained.
- A local project Git repository and GitHub Actions checks now exist. No remote has been configured or pushed; CI execution requires a remote repository.
- Automated accessibility checks do not replace a screen-reader or learner comprehension study.

## Runtime limits

Kernel confinement requires Linux 6.7+ on x86_64. `guard` is development only and is refused in production mode. This machine blocks Chromium's own sandbox; Landlock/seccomp provide confinement for generated render checks. Vision quality, extracted equations, source fidelity and pedagogical usefulness still require human review. Browser animations may run slowly under software WebGL.
