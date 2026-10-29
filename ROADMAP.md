# Implementation roadmap

The project is currently a **working local dashboard + simulated monitoring runner**, not a completed checkout bot.

## Delivered (v0.2)
- Responsive Overview, Tasks, Stores, Profiles, Logs and Settings.
- Real API/SQLite task CRUD, profile CRUD, store toggles and task bulk operations.
- Bounded concurrency; same-site pacing, backoff, cancellation; no restart auto-resume.
- Event logs, detail drawer, filters, settings export, command palette, light/dark.
- Localhost-only default, CSRF-origin/header checks, no external CDN.
- Tests covering CRUD, runner bulk controls, error responses and input validation.

## P0 — readiness before real use
- Add login/session protection before any remote/mobile access; TLS and secret management if deployed.
- Encrypt sensitive profile fields at rest, migrate plaintext SQLite data, and add backup/restore.
- Add scheduled periodic retention and structured error reporting.
- Integrate an adapter registry healthcheck and smoke tests per website.
- Introduce a central queue for restarts/multi-process execution if needed.

## P1 — user experience
- Task grouping, saved filters, sortable columns, import/export tasks.
- Enriched alert delivery and rate-limited Discord notifications.
- Site-specific fields and validation schemas rather than universal free-text task form.
- Activity chart based on dedicated daily counters, not a 100-log sample.
- Accessibility audit and screenshot regression suite.

## P2 — integrations
- For each store, confirm terms and any supported APIs, then implement strictly limited stock read/check adapters.
- Add real adapter integration tests with mocked HTTP responses, retry budgets and failure states.
- If a user-approved purchase handoff is later desired, design it separately from stock detection.

## Out of scope for this prototype
- Live store logins, queue or captcha circumvention, cart operations and auto-checkout.
- Reverse-engineered / undocumented private APIs.
