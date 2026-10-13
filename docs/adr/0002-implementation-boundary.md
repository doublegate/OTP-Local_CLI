# ADR 0002: Build a small local Python companion

- Status: Accepted by operator, 2026-10-12
- Date: 2026-10-11

## Context

The historical fish examples combine selection, JSON parsing, code retrieval and
clipboard side effects. This makes validation and failure behavior difficult to
test consistently. Python 3.14, fish and required native tools are already present.

## Decision

Implement a standard-library Python CLI with explicit scope and a bounded
subprocess layer. Provide thin fish wrappers. Delegate code generation to `op`;
do not implement TOTP, authentication, vault storage or a background service.

## Options considered

| Option | Tradeoff |
|---|---|
| Fish-only helpers | Smaller initial footprint; more difficult structured parsing/failure tests |
| Python standard library | Strong local test seams and structured validation; needs packaged launcher |
| Rust binary | Strong type/resource control; larger implementation/build commitment for this scope |
| Direct op only | Useful manual fallback; does not provide the specified selector/install/error contract |

## Consequences

Runtime dependency surface remains small. The project must test process limits,
environment inheritance, cancellation and installer conflicts. Python memory is
not claimed to provide secure zeroization. No extra network API is introduced.

## Actions

Implementation choice confirmed; build synthetic fake-tool tests first; enforce
[CLI contracts](../specs/03-cli-specification.md) and
[installation contracts](../specs/06-installation-and-instantiation.md).
