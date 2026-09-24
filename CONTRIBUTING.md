# Contributing

Thanks for your interest in improving this portfolio project.

## Ground rules

- Use **fictional data only**. Never add real employee data, customer data, proprietary vendor content, credentials, tokens, certificates or real endpoints.
- Write code, comments, docs and commit messages in English.
- Keep changes small and focused, with tests.

## Development workflow

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
make check                       # ruff lint + format check + pytest
```

## Pull requests

1. Create a branch from `main`.
2. Add or update tests for behavior changes.
3. Update documentation (`README.md`, `docs/`) when behavior or contracts change.
4. Record significant architectural decisions as a new ADR in `docs/adr/`.
5. Ensure CI is green.

## Commit messages

Use the imperative mood, e.g. `Add retry jitter to connector policy`.

