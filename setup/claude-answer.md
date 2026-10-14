# Explain what make test does

`make test` runs the `test` target in the repository's `Makefile`:

```make
test:
	pytest -q
```

- It runs **pytest** in quiet mode (`-q`), so the output shows one character per test and a short summary instead of every test name.
- pytest discovers and runs all tests under `tests/` (files named `test_*.py`), e.g. `tests/test_smoke.py`.
- `pyproject.toml` sets `pythonpath = ["."]`, so tests can import the `app` package from the repository root.
- The command exits with code 0 when all tests pass and non-zero when any test fails, which is what CI and `make` use to decide success.

`make test` does not validate the API contract; that is `make lint-contract` (`python tools/lint_contract.py docs/openapi.yaml`).
