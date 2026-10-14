# Contributing Guidelines

Thank you for contributing to Authy-to-1Password Local. To maintain the integrity, security,
and quality of this privacy-critical repository, all contributions must adhere to the following
standards.

## Core Mandates

- **Read Before Write**: Inspect existing implementations and tests before making modifications.
  Match the surrounding code style, naming patterns, and comment density.
- **Strict Zero-Emoji Policy**: No emojis are permitted anywhere in code, commits, comments, PRs,
  or documentation. Use precise technical language.
- **Never Commit Real Secrets**: Never commit or submit real OTP seeds, authentic tokens,
  private keys, or personal identifiers. Use synthetic fixtures and RFC 6238 golden vectors.
- **Fail-Closed Operations**: Validate external inputs at system boundaries. Convert unvalidated
  bytes to bounded, validated types once at the perimeter.

## Development Setup

The project requires Linux and Python 3.14:

```sh
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install development dependencies and editable package
pip install -r requirements-dev.txt
pip install --no-build-isolation --no-deps -e .
npm ci --ignore-scripts

# Verify bundled operator guides
python scripts/bundle_guides.py --check
```

## Commit Conventions

All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/)
specification:

- **Format**: `type(scope): subject`
- **Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`
- **Subject**: Imperative mood, lower case, no trailing period, maximum 72 characters.
- **Body**: Explain the technical motivation and *why* behind the change.

## Quality Gates

Before submitting a pull request, ensure all local validation gates pass cleanly:

```sh
# Run comprehensive CI validation suite (builds wheel, runs 1,258 tests + coverage + linters + smoke)
bash scripts/check.sh

# Run performance microbenchmark suite (verifies all 7 hot-path SLAs)
.venv/bin/python benchmarks/run_all.py

# Or execute individual quality gates:
.venv/bin/ruff check --no-cache src tests scripts benchmarks
.venv/bin/ruff format --no-cache --check src tests scripts benchmarks
npx markdownlint-cli2
.venv/bin/python scripts/check_docs.py
.venv/bin/pytest -o cache_dir=/tmp/pytest_cache -q
```
