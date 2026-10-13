# Pull Request

## Description

Concise technical explanation of the change and the motivation behind it.

## Type of Change

- [ ] `feat`: New capability or feature
- [ ] `fix`: Bug fix
- [ ] `docs`: Documentation update or addition
- [ ] `refactor`: Code refactoring without behavior change
- [ ] `test`: New or modified tests
- [ ] `chore`: Maintenance, dependencies, or tooling
- [ ] `perf`: Performance improvement

## Quality Gates Checklist

- [ ] All code conforms to existing style and naming patterns.
- [ ] Commit message follows Conventional Commits: `type(scope): subject`.
- [ ] Strict zero-emoji policy upheld across code, commits, and comments.
- [ ] No real secrets, tokens, or credentials are included or committed.
- [ ] Format check passes: `ruff format --check src tests scripts`
- [ ] Lint check passes: `ruff check src tests scripts`
- [ ] Markdownlint passes: `npx markdownlint-cli2`
- [ ] Documentation check passes: `python scripts/check_docs.py`
- [ ] Full test suite passes: `pytest -q`
- [ ] `CHANGELOG.md` updated under `[Unreleased]` if user-facing behavior changed.
