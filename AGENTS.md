<!-- Managed by Master-Claude. Universal rules come from the imported/inlined core.
     Edit only inside the MC-PROJECT block; mc-sync overwrites everything else. -->
<!-- mc-core: 0.2.0 | mode=inline | lang=generic -->
# AGENTS.md — Authy-to-1Password_Local

# Agent Working Agreement (Master-Core base)

> Universal, always-applied rules. This is the only content guaranteed to reach every agent in
> every install mode — keep it short and load-bearing. Heavier topic modules live in
> `master-core/modules/` (Claude `@import`s them; `--inline` bakes them in).

## Operating discipline

- **Read before write.** Inspect a file (Read/Grep/Glob) before editing; never blind-overwrite.
  For destructive or hard-to-reverse actions, confirm first unless explicitly authorized.
- **Curate, don't dump.** Prefer the smallest correct change. Match the surrounding code's
  style, naming, and comment density. Reuse existing utilities before writing new ones.
- **Report faithfully.** If tests fail, say so with the output. If a step was skipped, say so.
  State done-and-verified plainly; don't hedge or overclaim.
- **No emojis** in code, commits, comments, or docs. Precise technical language.

## Git & commits

- **Conventional Commits**: `feat|fix|docs|refactor|test|chore|perf|build|ci(scope): subject`,
  imperative, <=72 chars. One logical change per commit.
- **Never commit or push unless explicitly asked.** When asked, branch off the default branch
  first if you are on it. Do not force-push to a shared branch.
- Keep `CHANGELOG.md` updated in the same change as any user-visible behavior.

## Quality gates (run before declaring done)

- Format + lint + test must pass. Treat lint warnings as errors where the project does.
- Add/adjust tests with the change; for accuracy-critical paths, write the failing test first.
- Profile before optimizing; don't micro-optimize without a measurement.

## Documentation discipline

- Update the relevant doc in the **same change** as the code (docs-as-spec).
- Record non-obvious cross-cutting decisions as short ADRs; don't bury rationale in commit logs.

## Security baseline

- Validate external input at boundaries; never `unwrap`/trust unvalidated data.
- Secrets via environment variables only; never hardcode; never leak secrets in errors or logs.
- Some rules are enforced by the harness, not by you: `permissions.deny` entries and the
  `guards/` PreToolUse hooks block destructive commands outright. A denial is a correct
  outcome, not an obstacle — read the reason and take the suggested route instead of
  looking for a way around it.

## Delegation

- Match the model to the work. Mechanical work does not need the most expensive model.
- Delegate down: **scout** (locate files/symbols, read-only) and **verifier** (run the
  quality gates and report verbatim) for chores; **sweeper** for a transformation that is
  already fully specified. Keep design, diagnosis, and judgement on the primary model.
- Delegate a broad search rather than running the sweep inline when the intermediate file
  listings would be noise; you need the conclusion, not the dump.
- Give a subagent an explicit spec. A subagent starts with a fresh context and cannot see
  the reasoning that led to the request, so ambiguity becomes a wrong uniform change.

## Project-specific section

Everything above is universal. Concrete build/test/lint commands, architecture facts, and
project gotchas belong in the per-project managed block of this file (`<<< MC-PROJECT-... >>>`)
or in `master-core/lang/<language>.md` for language defaults — not here.

# Language Overlay — Generic (fallback)

Use when no language-specific overlay fits, or for polyglot/infra repos. Replace the
placeholders with the project's real commands in the per-project managed block.

## Discover the project's commands first

- Look for a `Makefile`, `justfile`, `Taskfile.yml`, `package.json` scripts, `scripts/`, or CI
  workflow (`.github/workflows/*.yml`) — the canonical build/test/lint commands usually live there.
- Mirror CI locally: whatever the CI gate runs is the source of truth for "green".

## Universal command slots (fill in)

- Build: `<project build command>`
- Test: `<project test command>` (+ how to run a single test)
- Lint / format gate: `<linter>` / `<formatter --check>`
- Coverage: `<coverage command>` (threshold enforced in CI)
- Security/deps audit: `<audit command>`; secrets via env only.

## Conventions

- Validate external input at boundaries; fail closed.
- Profile before optimizing; measure, don't guess.
- Keep docs and CHANGELOG in sync with behavior changes.

> Universal rules: see `master-core/AGENTS.base.md`. Topic depth: `master-core/modules/`.


---

# 10 — Commits, Versioning & Git Workflow

Conventions for commit messages, branches, and version numbers so history stays machine-readable and releases stay safe.

- Write every commit as a Conventional Commit: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`; optional `(scope)`.
- Keep the subject imperative, short, no trailing period; explain why in the body, not the subject.
- Mark breaking changes with `!` after type/scope or a `BREAKING CHANGE:` footer.
- Never commit unless the user explicitly asks; stage and describe, then wait.
- Run format, lint, and tests before committing; pass the same gate CI runs.
- Name branches `<type>/<short-desc>` (optionally `<user>/<type>/<desc>`), cut from the default branch.
- Never force-push the default branch; rebase your own branch onto upstream before review.
- Keep each commit one focused logical change; avoid catch-all commits across subsystems.
- Version with SemVer MAJOR.MINOR.PATCH: breaking → MAJOR, additive → MINOR, fix → PATCH.
- Ship additive, off-by-default changes as MINOR; keep default-build behavior unchanged.
- Update the CHANGELOG in the same change as any user-visible behavior; collect under `[Unreleased]`.
- Reference the ticket/issue ID in commits and PRs.
- In PRs, state motivation, list concrete changes, and note which checks you ran.
- Size tag messages and release notes to the release: summary + key changes minimum; more for headline releases.

> Language commands: see master-core/lang/<lang>.md

---

# Module 20 — Test-Driven Accuracy

Terse, project-agnostic rules. Apply when correctness must match an external oracle.

## Test-as-spec

- Pin the failing test (or oracle vector) FIRST; implement only until it passes.
- Treat tests and golden vectors as the spec. If docs and a test disagree, the test wins — fix the docs.
- Keep the spec doc and the code in sync in the same change; never let them drift apart.
- Make accuracy-critical behavior verified against an independent, external oracle, not self-asserted.

## Golden vectors

- Commit canonical reference outputs (framebuffers, logs, audio, encode/decode results).
- Update a canonical vector ONLY on intentional, reviewed behavior change. Accidental drift invalidates all prior results.
- Use one shared vector set to enforce parity between two implementations or code paths.
- Commit permissive/public-domain fixtures; gitignore proprietary oracles; degrade gracefully when absent.

## Determinism

- Hard contract: same seed + same input ⇒ byte-identical output.
- Inject seeds explicitly; preserve them across save/restore and replay.
- Keep wall-clock, OS RNG, thread scheduling, and unordered-map iteration order out of the core.
- Put rate control / timing jitter in the frontend, never in the deterministic core.

## Test layers

- Write unit tests in-module for single behaviors.
- Write integration tests in a separate suite for composition across modules.
- Add property-based tests for invariants (round-trips, idempotence, ordering).
- Add fuzz targets for parsers and any untrusted-input boundary.

## Exactness honesty

- Never present approximate output as exact.
- Propagate an exactness/confidence flag to every label, log line, and docstring.
- Add an honesty gate so the suite cannot claim support or accuracy it does not actually verify.

## Running suites

- Never run large suites unfiltered; scope by crate, file, or test-name substring.
- Run the full suite only in CI or pre-release.
- Run serially when debugging flakes.

## Gates

- Gate merges on a coverage threshold to prevent silent erosion.
- Add a regression gate for any fixed bug (the pinned test stays).

## Project-bound (keep in project stub, not here)

- Exact pass counts, percentages, named suites/corpora.
- Specific oracle tools, reference cores, hardware models.
- Per-project exact-vs-approximate feature flags.
- Performance baselines and timing budgets.

> Language commands: see master-core/lang/<lang>.md

---

# 30 — Quality Gates, CI/CD & Performance

Automated merge gates (format, lint, test, coverage, multi-platform build) plus profile-first performance discipline.

- Run format and lint as blocking gates; treat warnings as errors.
- Run the full suite (unit, integration, doc/example tests) in CI on every PR.
- Reproduce the CI gate locally with the same commands before opening a PR.
- Enforce a coverage floor for the repo and a higher bar for core logic; fail on drops below the floor.
- Fuzz untrusted-input and parser/protocol paths continuously; gate crash count at zero.
- Build and test across a platform matrix, including a pinned minimum-toolchain job.
- Build distributables for every supported platform/arch (cross-compile, multi-arch images) and smoke-test them in CI.
- Guard CI dependency installs with presence checks so reruns stay idempotent.
- Gate docs too: build with warnings-as-errors and compile doc examples.
- Use path filters / conditional jobs so doc-only changes still report required checks as passed.
- Profile before optimizing; never optimize on a hunch — capture a benchmark or flamegraph first.
- Change only the measured hot path, then re-measure.
- Keep hot paths allocation-free and abstraction-light; prefer fixed buffers over per-iteration allocation.
- Document the before/after number for every performance change.
- Gate against performance regressions, not only correctness; fail CI on tracked-benchmark slowdowns.

> Language commands: see master-core/lang/<lang>.md

---

# 40 — Docs-as-Spec, ADRs, CHANGELOG, ROADMAP

- Treat subsystem docs as the spec, not a history log.
- Update the matching `docs/<subsystem>.md` in the SAME change as any behavior change.
- Reject a behavior diff whose spec is left untouched; enforce via a contribution gate.
- When an executable oracle (test, golden output, conformance suite) and the prose disagree, fix the prose.
- Designate exactly one status file as the single source of truth for current state.
- Let narrative summaries lag, but point them at the canonical status file.
- Write ADRs in Michael Nygard format: Context, Decision, Consequences.
- Capture rationale and cost in ADRs, not changelog-style history.
- Store ADRs numbered under `docs/adr/`.
- Never rewrite a superseded ADR in place; add a new ADR that supersedes and cross-links it.
- Keep one CHANGELOG.md as the single source of truth for user-visible change.
- Maintain an `[Unreleased]` section; add the entry in the same PR as the user-facing change.
- Enforce the CHANGELOG entry with a quality gate; rename `[Unreleased]` to the version at release.
- Keep deep engineering/lineage narrative out of the CHANGELOG.
- Keep README to: platform/support matrix, quick-start, one-paragraph architecture sketch.
- Make README point to status and subsystem docs instead of restating them; refresh it as a release task.
- Use ROADMAP.md as the planning entry point and the place stable ticket IDs are minted.
- Assign every roadmap item a stable, citable ID and reference it in branches/commits/PRs.
- Treat the reference/research corpus as immutable.
- Land corrections to immutable references as new dated supplemental files, never in-place rewrites.
- Mark immutable/vendored trees exempt from linters and reformatters.
- Build docs in CI with warnings-as-errors so examples and intra-doc links stay valid.
- Avoid intra-doc links to feature-gated deps in default doc builds; use plain code spans.
- Pin the markdown linter version in the gate; a newer local binary may report ungated rules.
- Disable lint rules that fight legitimate long technical tables or HTML banners by design.

---

# Module 50 — Architecture by Ownership

Terse, project-agnostic rules for stateful-system structure, data, and errors.

## Ownership of mutable state

- Give ONE component (Bus / Scheduler / context) ownership of all mutable subsystems.
- Have every other component borrow it (`&mut` or a scoped handle) for the duration of a step.
- Hand each consumer the narrowest interface it needs, not the whole owner.
- This avoids the "A holds B but B needs A" cycle and lock-ordering bugs.

## Dependency graph

- Keep the graph strictly one-directional; no cross-module cycles.
- Let a single top-level unit tie the lower units together.
- Ensure each unit compiles, tests, fuzzes, and benchmarks in isolation.
- Reject any back-edge that makes a unit depend on a peer.

## Timing / scheduling

- Use a single clock/timing master; advance every subsystem on its divisor (lockstep, not catch-up).
- Keep all timing authority in one scheduler so mid-step cross-subsystem events work without per-quirk patches.

## Abstraction boundaries

- Abstract boundaries with traits/interfaces, not concrete structs.
- Provide default no-op hooks for optional behavior.
- Gate mock / test-only seams behind a test or feature flag so release paths are unchanged.

## Safety

- Require a `// SAFETY:` comment on every unsafe / FFI block stating the upheld invariant.
- Confine unsafe to as few modules as possible (frontend, FFI shim).

## Feature flags

- Make additive features default-off.
- Keep shipped/native/portable/wasm builds byte-identical when optional features are off.

## Database

- Treat one database as the source of truth; enable WAL (or equivalent) for concurrent reads.
- Use an ORM / query builder / parameterized statements; never concatenate SQL strings.
- Apply schema changes via versioned, ordered, replayable migrations; record the version.
- Expose read-only query surfaces; allow JSON/YAML config overrides with documented precedence.

## Error handling

- Return a typed result/optional from fallible operations; reserve panics for true invariants.
- Never unwrap/assert on untrusted input; validate and convert to a typed error.
- Include context in error messages (what failed, which input, why); never leak secrets.

## Project-bound (keep in project stub, not here)

- Subsystem/chip names, clock frequencies, divisor ratios.
- Crate/package layout, binary names, layer topology diagrams.
- ORM/table names, migration counts, feature-flag names.

> Language commands: see master-core/lang/<lang>.md

---

# 60 — Security & Input Validation

Project-agnostic security rules. Imperative, decision-based. See `docs/knowledge/60-security.md` for rationale.

## Input validation

- Validate ALL external input at the boundary; trust only the parsed, typed value inward.
- Prefer allowlists over denylists; enumerate what is permitted.
- Parse-don't-validate: convert raw bytes/strings to a range-checked type once, at the edge.
- Bounds-check every length/offset/tag read from untrusted bytes before use.
- Return `Result`/`Option`/error-union on malformed input; never `unwrap`/`panic` on external data.
- Reject unsupported inputs explicitly; never stub an unimplemented path as if it worked.

## Privilege

- Acquire elevated privilege only for the operation that needs it.
- Drop privileges immediately afterward; minimize the privileged-and-parsing window.
- Process untrusted input only in an unprivileged context.
- Prefer least-privilege capability tokens over ambient/global authority.
- Make capability tokens unforgeable and revocable (generation/version marker).

## DoS prevention

- Bound concurrency with a semaphore; cap in-flight operations.
- Throttle issuance with a token-bucket rate limiter; allow a small burst.
- Stream large I/O to disk; never buffer unbounded data in memory.
- Use adaptive limits that stay responsive while bounding worst case.

## Secrets & errors

- Load secrets from environment/secret store; never hardcode; never commit.
- Keep secrets, keys, tokens, and internal detail out of logs and error messages.
- Error messages state what failed plus a correlation ID, not sensitive values.

## Hardening & release gates

- Fuzz every parser that ingests untrusted input; goal = no input crashes it.
- Run a fixed security-audit checklist before each release.
- Run dependency vulnerability audits on a recurring cadence, not once.
- Test security/offensive tooling on every supported platform; document expected differences.
- Require explicit confirmation for destructive/high-blast-radius operations.
- Write an audit-log entry (who/what/when/scope) before performing dangerous actions.

## Out of scope here (keep in project stub)

- Exact burst sizes, concurrency caps, timeouts, zero-copy thresholds.
- The concrete privilege/capability model and elevation-requiring syscalls.
- Project-specific "never commit X" rules and env-var/secret-store names.
- Single-tool platform quirks.

---

# 70 — Release Ceremony

- Gate every cut behind a deterministic pre-release checklist; fail closed on hard failures.
- Require before tagging: clean tree, tests green, linter clean, docs build, CHANGELOG updated, no advisories, CI green, versions consistent.
- Emit a PASS/FAIL/WARN tally and a written report from the pre-release gate.
- Detect an existing tag/release before creating one; never double-ship a version.
- Treat a published version as immutable; bump or explicitly delete a stale tag instead of overwriting.
- Make the annotated tag a standalone artifact: executive summary plus technical depth.
- Include in the tag: features, metrics deltas, technical details, files changed, testing evidence, value.
- Extend release notes beyond the tag with install steps, platform matrix, asset links, known issues, upgrade notes.
- Follow SemVer: MAJOR breaking, MINOR additive, PATCH bugfix/polish.
- Keep feature work additive and off-by-default so non-major releases stay compatible.
- Reserve breaking save-state/format/API changes for one clearly-announced major release flagged in advance.
- Maintain an explicit per-release packaging matrix: multi-arch images, OS packages, per-triple binaries, man pages, checksums.
- Build all artifacts from a release workflow so the set is reproducible, not hand-assembled.
- Trigger release builds on the version-tag push; redeploy docs/demo sites on the same tag.
- Expose a manual `workflow_dispatch` trigger; keep release/docs builds idempotent.
- Stage the rollout: ship beta/sideload/TestFlight channels before production/GA.
- Document kill/rollback criteria in writing before a staged rollout begins.
- Defer the production launch flags until the stabilizing release; flip them all at the final launch version.
- Fix a written, ordered release process and follow it every time.
- Typical order: assemble notes from sprint/phase docs, review commit range, run gate, tag, release with assets, verify, push.
- Derive the version from the build manifest; assert it matches README and any embedded version checks before tagging.
- Cross-compile platform binaries via target triples; use vendored TLS for static musl builds.
- Attach checksummed assets; pin toolchains in the release pipeline.

---

# 80 — Phase / Sprint Workflow

- Organize work as long-lived phases subdivided into short sprints.
- Make Phase 0 foundation and the final phase polish/release; group coherent capability sets in between.
- Treat the sprint as the unit of execution; name it `phase.sprint` or descriptively, and accept both forms in tooling.
- Give every work item a stable ticket ID (e.g. `T-PS-NNN`) minted in the roadmap.
- Cite the ticket ID in branches, commits, and PRs across the item's whole lifecycle.
- Run the sprint lifecycle: start, execute, complete, report.
- On start: validate the sprint-ID format, resolve any existing-dir conflict (continue/archive/abort), scaffold plan + task checklist + notes.
- On execute: work the checklist.
- On complete: validate readiness (all tasks checked, full suite green), prompting before any override.
- On complete: gather test/code/git metrics, update docs and version, prepare the commit.
- On report: write a completion summary.
- Make every gate fail-loud; never let a sprint complete with red tests silently.
- Close a phase with a heavier ceremony: gap analysis, full doc pass, quality validation, tag + release, final verification.
- Cut a version at the phase close, not mid-sprint.
- Keep one durable PROJECT-STATUS.md with a fixed skeleton.
- Status skeleton: exec summary, phase matrix, feature/capability matrix, metrics snapshot, timeline, known issues, prioritized remaining work, next steps, readiness checklist.
- Update the durable status file at every sprint and phase boundary.
- Put volatile session state in a separate CLAUDE.local.md, never in the durable docs.
- Local session state: timestamp, current metrics snapshot, recent decisions (~30d), recent sessions (~7d), live sprint progress.
- Migrate stable decisions from the local file into the durable historical-decisions table.
- Maintain a metrics snapshot table (tests, coverage, latest release, CI cadence, active sprints) with a named source per row.
- Keep badges, status file, and session file numbers in sync on every status change.
- Propagate each behavior-changing sprint into guide docs, README tables, and any mirror in the same change.
- Gather metrics from test output and `git diff --stat`; gate completion on format + lint + full test run mirroring CI.
- Scaffold sprint workspaces and reports in a scratch dir, not in the repo.

> Session-state template: templates/CLAUDE.local.md

---

# 90 — Multi-Language Integration

Project-agnostic rules for polyglot systems (FFI, shared contracts, cross-language parity). See `docs/knowledge/90-multi-language-integration.md` for rationale.

## Shared contracts

- Define each shared shape (message/record/API) ONCE in a schema/IDL.
- Generate per-language bindings from that schema; never hand-maintain parallel copies.
- A schema change must force every consuming language to update.

## FFI / native boundaries

- Keep the FFI surface thin and concentrated in one module, not scattered.
- Put a `// SAFETY:` comment on every unsafe/native call stating the invariant relied on.
- Name who guarantees each invariant (pointer validity, length, lifetime, null-termination).
- Wrap vendored native libraries behind a single explicit shim layer.

## Cross-language parity

- Pin duplicated logic (same algorithm in two languages) to one shared golden-vector set and assert via a parity test that both implementations match it.
- Module 20's *Golden vectors* and *Exactness honesty* rules are canonical — apply them here; do not restate per language.

## Type-safe boundaries

- Use a typed contract (typed RPC / generated client) between your own services.
- Make a field rename a compile error, not a runtime 4xx.
- Reserve untyped REST/JSON for the true external perimeter only.
- Fix the stream/transport contract: results vs diagnostics on separate streams, defined framing/encoding.

## Per-subproject toolchain

- Each language keeps its own linter, formatter, and test runner.
- Provide one aggregate gate that runs every language's checks and fails if any fails.
- Do not impose one language's conventions on another.

## Platform & feature variation

- Gate OS/arch/optional-dependency differences behind explicit conditional compilation / feature flags.
- Define behavior for every branch, including the "native extension absent" fallback.
- Test both the native-present and fallback paths.
- Keep the core dependency-light (ideally stdlib-only); push native/heavy deps behind an opt-in extra.

## Out of scope here (keep in project stub)

- The specific schema technology and generated-language list.
- Which files are parity pairs and where golden vectors live.
- Native build steps, feature-flag names, stream contract, target matrix, verify-all command.

---

# 91 — Agent & Assistant System Architecture

Project-agnostic rules for building systems where an LLM is a component, not the product:
assistants, agents, orchestrators, MCP servers, and memory services. Applies when you ship
the harness; keep detailed rationale in the project's accompanying architecture documentation.

## Layering

- Split responsibilities into five layers: **LLM, Memory, Tooling, Routing, Observability**.
- Give each layer one owner and one interface; do not let a prompt string carry routing,
  retrieval, and tool policy at once.
- Define the system's contract above the model call: request = intent + identity + session +
  attachments + policy; response = answer + actions + citations + state changes + trace id.
- Start with one orchestrator, one durable memory path, one trace per request, one tool policy.
  Add multi-agent topology only after single-agent failure cases are explainable without guessing.

## Tool boundary

- Treat tool use as a contract: the model emits a structured request, the runtime executes, the
  result returns to the context. The model never executes anything itself.
- Define every tool with a strict schema and validate arguments at the boundary. A sloppy tool
  boundary makes the whole assistant sloppy.
- Make tool handlers idempotent and give mutating tools an idempotency key; retries are normal.
- Gate side-effecting tools behind an explicit approval step, not behind prompt wording.
- Expose external capabilities through a standard protocol (MCP) rather than a bespoke connector
  per system; keep the agent-to-integration seam replaceable.

## Memory

- Separate the tiers explicitly: **working** (current task scratch), **session** (conversation),
  **durable** (survives sessions). Do not collapse them into "longer context".
- Define read-after-write visibility per tier and write it down. "Memory updated" and "memory
  visible to the current answer" are different truths; a frozen session snapshot preserves
  prefix-cache performance but hides writes made during the turn.
- Promote to durable memory through review, not automatically. An unreviewed write is how a
  wrong fact becomes permanent and reaches every future session.
- Retrieval is not a longer prompt: budget context, rank, and place decisive facts early.
  Recall degrades in the middle of a long context regardless of the window size.
- Evaluate retrieval as its own component with its own metrics, separately from generation.

## Routing

- Route on more than model choice: provider path, tenant, budget, latency class, and fallback.
- Give the router explicit policies (weighted, least-busy, latency-based, cost-based) and
  bounded failover; an unbounded retry chain is an outage amplifier.
- Use auxiliary model slots for chores — summarization, compression, classification, routing —
  and reserve the primary model for the reasoning the product is actually selling.
- Keep sessions sticky where behavior consistency matters; route per-request only where it does not.

## Observability

- Emit one trace per request, one span per model call, one event per tool execution. A system
  without these is not observable, whatever its dashboards show.
- Record for every request: which context was assembled, which tool ran, which model answered,
  which memory was read or written. Every production disagreement reduces to one of these.
- Track cost and token usage per route and per tenant, not only in aggregate.
- Gate changes to prompts, routes, retrieval, and memory policy behind regression evals. Prompt
  changes are code changes and deserve the same regression-evaluation gate.

## Failure modes → mitigation

| Symptom | Usual cause | Mitigation |
|---|---|---|
| Confident but off-target answer | irrelevant or badly ordered context | budget context, rerank, put key facts early |
| Right tone, wrong facts | bad chunking, stale index, weak filters | evaluate retrieval separately; metadata filters, hybrid search |
| Wrong or duplicated action | loose schemas, retries without idempotency | tight schemas, idempotency keys, approval gates |
| Behavior varies per request | cost/latency routing without quality control | sticky sessions, per-route evals |
| Stale or poisoned recall | over-eager writes, weak review, cross-session leakage | separate tiers, review promotions |
| Cannot explain an incident | missing traces or coarse spans | root span plus subspans for retrieval, model, tool |
| Plausible unsupported claims | weak grounding, no validation pass | reference-doc validation, self-consistency checks, eval gates |

## Harness safety (when your system runs agents)

- Enforce policy in the runtime, not in the system prompt. Instructions shape what an agent
  tries; only the runtime decides what it may do.
- Run untrusted-input parsing and tool execution with the narrowest privilege that works.
- Log every privileged or destructive action with who, what, when, and scope before it runs.
- Assume any content a sub-component reads may carry injected instructions — including diffs,
  retrieved documents, and tool output. Never let retrieved text change permission decisions.

## Out of scope here (keep in project stub)

- Named vendors, model IDs, pricing, and context-window sizes.
- Concrete vector store, gateway, proxy, and tracing-backend choices.
- Per-project latency budgets, token ceilings, and route tables.
- The specific schema technology for tool contracts.

> Language commands: see master-core/lang/<lang>.md

---

# 95 — Named Pattern Library

Reusable, project-agnostic named patterns. See `docs/knowledge/95-named-pattern-library.md` for full structure and rationale.

## The discipline

- Give every recurring solution a stable, capitalized Name — a token humans and agents can invoke.
- Record each pattern as: Name — Problem — Solution — Implementation — Evidence/rationale — Applies-to.
- Patterns are mechanisms, not measurements; abstract away hardware limits, chip names, and repo jargon.
- One Name = one definition; add a new Name rather than silently redefining one.
- Deduplicate: merge entries that differ only by domain under the more general Name.
- A pattern without a rationale is just a rule — record the pain it prevents.

## Catalog (Name — when — rule)

- Central-State Ownership — cross-cutting mutable state — give each long-lived state one owner; mutate only through a single controlled, lock-guarded handle.
- Read-Before-Write — modifying any existing artifact — read and understand current content first; edit in place; full-write only for new files.
- Dry-Run-First Destructive Op — bulk/irreversible operations — default to a no-op preview that reports what would change; require explicit opt-in, backup, confirmation, and an audit entry to execute.
- Golden-Vector Parity — behavior that must stay constant across languages/versions — pin to canonical input→output vectors, assert in CI, change a vector only on intentional behavior change.
- Managed-Block Generated-vs-Hand-Authored — codegen/sync into a file with hand-written content — confine machine writes to explicitly marked regions; preserve everything outside.
- Feature-Flag Additive Change — new/risky capability — land it off-by-default so default builds stay behavior-identical; promote only after it proves out; test both paths.
- Context-Aware Validation — systems with multiple valid modes/profiles — detect the current mode first, validate against that mode's expectations, flag only genuine mismatches.
- Progressive-With-Rollback — applying an extreme/risky setting — step toward the target, validate stability at each step, auto-roll-back on failure (abstract the limit; never hardcode it as the pattern).

## Out of scope here (keep in project stub)

- Patterns whose substance is a specific number/limit, chip, OS feature, or package manager.
- A local Name for something already covered above — cross-reference instead.
- Exact paths, marker syntax, or vector locations a single repo uses.

<<< MC-PROJECT-START >>>

## Project: Authy-to-1Password_Local

- **What it is:** Local terminal companion, migration engine, and security layer for accessing two-factor authentication (TOTP/HOTP) tokens across 1Password, local GPG `pass-otp`, Apple Secure Enclave & macOS Keychain, hardware TPM 2.0 enclaves, and YubiKeys.
- **Current stack:** Python 3.14 package on Linux (CachyOS/Arch, Ubuntu, Debian, Fedora) and macOS (Darwin Apple Silicon and Intel). Textual TUI dashboard, CLI commands, fish wrappers, reversible offline installer, six credential backends (1Password, pass-otp/GPG, totpm/TPM 2.0, YubiKey OATH, hardware TPM 2.0, and macOS Keychain via `/usr/bin/security`).
- **Build / test / lint:** Prepare the project .venv and local npm tools as in docs/05-development-and-testing.md, then run `ruff check src tests scripts`, `ruff format --check src tests scripts`, `npx markdownlint-cli2`, `python scripts/check_docs.py`, `python scripts/bundle_guides.py --check`, `pytest tests -v`, and `python scripts/smoke_package.py`. The full suite contains 718 tests with 100% pass rate.
- **Documentation & Linting checks:** Run `python scripts/check_docs.py` and `npx markdownlint-cli2`. Note: `.markdownlint-cli2.jsonc` requires `"MD024": { "siblings_only": true }` to permit standard Keep a Changelog subheadings (`Added`, `Fixed`, `Changed`) across multiple release versions in `CHANGELOG.md`.
- **macOS Hardware & Doctor Remediation:** Apple hardware utilizes Apple Secure Enclave Processor (SEP) and macOS Keychain (`/usr/bin/security`) rather than PC TPM 2.0. On Darwin, discrete PC TPM components (`totpm`, `tpm2-totp`, `tpm-device`) are reported as `not-applicable`. `otp-local doctor --install` (or `--fix`) automatically remediates missing capabilities via Homebrew with 10MB process output caps and 900s execution deadlines.
- **Packaging & Installation:** Packaged as `authy-local` v1.1.0. For modern environments enforcing PEP 668, recommend `uv tool install --editable .` or `pipx install .`.

### Intended operating model

- The runbook prefers one authoritative TOTP seed in 1Password, with terminal access through `op item get ITEM --otp`.
- Supported backends: 1Password (`onepassword`), local GPG (`pass-otp`), hardware TPM 2.0 (`totpm`), physical YubiKey (`yubikey`), TPM2 (`tpm2-totp`), and macOS Keychain (`keychain`).
- Preserve 1Password terminal session identity. Vendor authorization is per account/terminal, expires after 10 minutes idle or 12 hours total and is revoked on lock.
- All secrets are piped via standard input into memory-locked in-process TOTP derivation; never pass secrets in process arguments (`argv`), environment variables, or error diagnostics.
- Never place real TOTP seeds, recovery codes, QR images, plaintext exports, vault contents, or credentials in this workspace, Git, logs, or model context.

### Where things live

- `README.md` — project entry point and navigation.
- `PROJECT-STATUS.md` — authoritative project progress and open decisions; update when evidence changes.
- `CHANGELOG.md` — single source of truth for user-visible changes across releases (v1.0.0, v1.1.0).
- `docs/00-index.md` — architecture, requirements, CLI/security contracts, installation, migration, operations and ADR navigation.
- `docs/03-cli-specification.md` — CLI command and backend specifications.
- `docs/08-optional-backends.md` — hardware TPM, GPG pass-otp, and macOS Keychain & Apple Secure Enclave specifications.
- `docs/11-tui.md` — Textual TUI design, keybindings, and modal hierarchies.
- `AGENTS.md` — canonical agent guidance; `CLAUDE.md` and `GEMINI.md` symlink to it. Edit project guidance only between the managed markers.
<<< MC-PROJECT-END >>>

