# AGENTS.md

## Project Rules

- This is a Windows desktop application.
- Use PySide6 for the GUI.
- Use SQLite and SQLAlchemy for local storage.
- Store user data in Windows AppData through `platformdirs`.
- Keep business logic outside UI widgets.
- Do not add a server, web backend, web frontend, Docker, PostgreSQL, Redis, Celery, FastAPI, Uvicorn, React, or Next.js.

## Architecture Rules

- `ui/` contains Qt widgets and dialogs only.
- `services/` orchestrates workflows.
- `connectors/` fetch and normalize external documents.
- `parsing/` extracts text from raw content.
- `event_engine/` contains deterministic matching, detection, dedupe, and scoring.
- `db/` owns SQLAlchemy models, sessions, repositories, and simple migrations.

## Security Rules

- All URL fetching must call `security.url_safety`.
- Only `http` and `https` are allowed.
- Block localhost, loopback, private IP ranges, link-local ranges, and metadata-service IPs.
- Re-check final URLs after redirects.
- Enforce timeout and maximum response size.
- Do not execute remote code or scripts.
- Do not log secrets.

## Packaging Rules

- Build with PyInstaller in onedir mode by default.
- Installer uses Inno Setup.
- The installed app must run without a Python installation.
- Keep icon use tolerant so builds do not fail if a placeholder icon is unavailable.

## Testing Rules

- Tests must not require external network calls.
- Use local fixtures and respx/httpx mocks.
- Run:

```bat
pytest
ruff check src tests
```

## Definition Of Done

- The desktop app launches from `run_dev.bat`.
- SQLite database is created automatically.
- Demo ingestion can create a document, event, evidence, and alert offline.
- CSV export works.
- `pytest` passes.
- `ruff check src tests` passes.
- `build.bat` creates the PyInstaller onedir app.
- Inno Setup script exists and can build an installer when `ISCC.exe` is installed.
