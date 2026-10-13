# ADR 0004: Cohesive standard-library terminal interface

Status: accepted by the operator on 2026-10-12.

## Context

The operator requested a Python TUI and integrated delivery in the same package.
The existing baseline uses Python 3.14 without third-party runtime dependencies,
explicit scope and private human-operated migration checkpoints.

## Decision

Add `otp-local tui` using standard-library curses. Offer doctor, show, copy,
selection, installation preview and migration guidance. Reuse CLI dispatch and
the installer preview API; do not duplicate backend or enrollment logic.

Scope forms and displayed codes are ephemeral. Suspend curses for external fzf
and native authorization, restore terminal state afterward, and erase displayed
results on dismissal. Installation apply stays outside the TUI. Checklist viewing
does not count as an operator attestation or authorize an account change.

Add sprint 2.3 before the Phase 3 pilot. Final package acceptance covers CLI,
TUI and fish wrappers together, including isolated installation and rollback.

## Consequences

No additional Python runtime dependencies are needed. Keyboard interaction and
minimum terminal dimensions are supported; richer Textual widgets are deferred.
Python memory and terminal emulators cannot guarantee secret zeroization.
Human synthetic acceptance remains mandatory before real migration.
