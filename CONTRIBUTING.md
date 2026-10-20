# Contributing

Use Python 3.10+, Node.js 20+, and optional native toolchains from README.

```sh
python -m venv .venv
# Activate .venv
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
python -m pytest -q
ruff check codescope tests
```

Add a regression test with each bug fix. New adapters must return the common finding schema and distinguish an absent/failed tool from a clean result. Never execute user programs, accept arbitrary build files, shell commands or compiler flags.

UI changes need keyboard, light/dark, desktop and 390px mobile checks. Text is primarily Russian; upstream diagnostic messages retain their original language. Do not claim a tool detects all bugs.
