# Contributing

Thanks for improving PhotoFinder. Keep changes focused and include tests for behavior changes.

## Development Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Test

```bash
./.venv/bin/python -m unittest discover -v
```

For frontend controller tests, Node.js is required because `tests/test_web_app_controller.py` runs `tests/web_app_controller_harness.js`.

## Privacy Rules

- Do not commit personal photo folders, generated thumbnails, SQLite databases, model downloads, API keys, or `.env` files.
- Use generic example paths such as `/Users/example/Pictures` or `/home/example/Pictures`.
- Put packaged binaries and archives in GitHub Releases instead of committing them to the repository.
