# Agent instructions — NEXUS Commerce Operations

## Goal
Advance the integrated local AIO monitoring dashboard. Preserve an elegant, high-density NEXUS design and a clean separation between UI, API, scheduler, database and site integrations.

## Non-negotiables
- Never represent demo results as real stock or checkout success.
- Real-site adapters and purchasing are not implemented. Do not silently claim otherwise.
- Do not disable local-only security controls to "make it work." An authenticated remote option is a separate future feature.
- No payment-card numbers, CVVs, passwords or tokens in SQLite, screenshots, logs or example data.
- Do not bypass retailer anti-bot controls or authentication gates. Respect permitted access paths and rate limits.
- Keep Python dependency count low, plain JS/CSS frontend and FastAPI backend.
- Preserve keyboard navigation, mobile responsiveness, Japanese labels, and dark/light support.

## Project map
- `app/main.py`: FastAPI routes / JSON validation / origin protection.
- `app/db.py`: SQLite schema and persistence.
- `app/runner.py`: bounded monitoring scheduler, cancellation, backoff, Discord notification.
- `app/adapters.py`: explicit adapter registry, no live implementations yet.
- `app/static/index.html`, `app.css`, `app.js`: responsive single-page UI.
- `tests/test_api.py`: API integration smoke tests.

## Verify before reporting completion
1. `python -m pytest -q` (install `requirements-dev.txt` first).
2. `node --check app/static/app.js` if Node is available.
3. Launch `start-demo.bat` or `DEMO_MODE=1 NEXUS_SEED_DEMO=1 python -m uvicorn app.main:app --host 127.0.0.1` and check Overview / Tasks / Stores / Profiles / Logs / Settings.
4. Inspect at 1440px and 390px widths.
5. Report implemented, simulated, and blocked features separately.

## Next priorities
See `ROADMAP.md`. Obtain explicit, documented interface details for any real retailer-specific monitoring before implementing it.
