# Phase 0 and 1 verification — 2026-10-12

Both phases are complete within their defined scope. Progress is authoritative
in [PROJECT-STATUS.md](../../PROJECT-STATUS.md). No later-phase account migration,
home installation or live companion OTP retrieval is claimed.

## Phase 0 evidence

- Operator accepted the 1Password default, Python 3.14 stdlib companion and
  synthetic-only automated testing baseline; ADRs 0001–0003 reflect that decision.
- Standalone repository initialized on `main`; host-level checks confirm correct
  root, no commit, no remote, no staged paths and zero tracked files yet.
- Read-only versions/help and host clock checks refreshed. NTP and synchronization
  are enabled; sandbox bus visibility remains limited.
- Operator attested on 2026-10-12: desktop unlock, scoped CLI approval, private
  ledger location and independent-recovery checklist all passed. Agents did not
  inspect private contents or independently reproduce those checks.
- Blank private-ledger/recovery template prepared; all eight Phase 0 tasks closed.

See [readiness evidence](../operations/2026-10-12-phase-0-readiness.md).

## Phase 1 evidence

| Gate | Result |
|---|---|
| Synthetic unit/integration suite | 52 tests pass |
| Branch-inclusive aggregate coverage | 97%; blocking floor 90% |
| Scope/code validator and 1Password adapter | 100%; blocking scoped floor 100% |
| Ruff lint and format | Pass, pinned 0.17.0 |
| Bash gate syntax/style | ShellCheck passes |
| Markdown | Pinned CLI2 0.23.3 passes authored documents |
| Documentation integrity | Local links, all 48 task IDs and reference hash pass |
| Packaging | Source distribution and wheel build with pinned tools |
| Wheel smoke | Isolated environment install; help/version work with no backend access |
| Dependency consistency | Project environment pip check passes; runtime dependencies empty |
| Local security review | No additional concrete defect found in reviewed Phase 1 boundary |

Canonical gate: `bash scripts/check.sh`. The developer entry point is
`.venv/bin/otp-local`; only doctor/show/help/version are implemented.
The real-host doctor was run without authentication and reported available
tools and unknown authentication/clock within the sandbox.

## Test-first and regression history

Initial package and runner tests failed before source implementation. Subsequent
real-PTY/fake-op tests exposed unsupported-platform/Python retrieval gates.
Independent review exposed oversized version parsing and repeated SIGINT cleanup
bugs; both were pinned failing before fixes. Closed-diagnostic-sink regressions
were likewise pinned before adding protected error writes.

Earlier coverage gates failed at 83% and 89%; additional meaningful terminal,
doctor cancellation and diagnostic-boundary tests brought the final result to 97%.
No failed mandatory gate remains. All eight Phase 1 tasks are closed.

Source-tree fingerprint (sorted relative Python paths, NUL, bytes, NUL):

```text
9ac9973a127b9b608a400b84fbffa65a7325d689db78557f839e82af0f59f880
```

## Limits and next boundary

Tests use synthetic codes, identifiers and fake executables; real terminal tests
do not contact 1Password. No real OTP, vault inventory or recovery material entered
agent context. Tool presence, human approval and fake-backend correctness are
different evidence categories.

Live account-ID shape and synthetic-item companion compatibility remain before
real use. Same-user/root compromise, replacement of trusted executables, deliberate
daemonization outside the owned process group and hard termination are outside
the cleanup/security guarantee. Python cannot guarantee memory zeroization.

Phase 2 adds selection, clipboard, fish wrappers and reversible home installation.
The original reference remains unchanged. No commit, tag, remote or publication
was performed; development environments and build artifacts are ignored.
