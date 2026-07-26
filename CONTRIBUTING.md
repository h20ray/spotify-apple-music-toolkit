# Contributing

## Setup

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
pip install -e ".[dev]"   # optional: black, flake8, mypy, pre-commit
```

Copy `.env.example` to `.env` and fill Spotify / Apple Music tokens as needed.

## Tests

```bash
pytest
pytest --cov=toolkit
```

## Style

- Black + isort (see `pyproject.toml`)
- Prefer specific exceptions + `logger` over bare `except Exception`
- UI output via Rich `console`; errors/warnings via `toolkit.core.logging`
- Magic numbers live in `toolkit.core.constants`

## Pre-commit (optional)

```bash
pre-commit install
pre-commit run --all-files
```

## PR checklist

- [ ] `pytest` green
- [ ] `python main.py` menu loads
- [ ] No `sys.exit` in library modules (dashboard exit OK)
- [ ] New public helpers have type hints
