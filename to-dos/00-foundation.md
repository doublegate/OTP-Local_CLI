# T-AUTH-002: operational preflight plan

Goal: make the first pilot reviewable without touching credentials or account MFA.
Track completion in [PROJECT-STATUS.md](../PROJECT-STATUS.md).

Legacy milestone checklist. The authoritative delivery tasks now live in
[sprints 0.1 and 0.2](README.md); do not maintain duplicate task completion here.
The current research and read-only host snapshot are in
[research evidence](../docs/specs/10-research-and-host-evidence.md). They do not complete
human authentication or recovery readiness. Phase 0 is now complete with separate
operator attestation; the prompts below are historical, not a second pending backlog.

- Resolve local version control: retain the ignored parent-workspace arrangement
  or explicitly authorize a standalone repository. Do not publish or create a remote.
- Confirm one authoritative seed in 1Password as the operating model, or record
  the specific need for an independent local fallback.
- Check current official documentation for the selected 1Password desktop/CLI
  integration and per-service re-enrollment flow. Record dated links in a new supplement.
- Perform a separately authorized read-only host preflight: executable presence,
  CLI version, and clock synchronization. Record pass/fail only; do not enumerate
  vault items, request OTPs, read seeds, or change system settings.
- Prepare pilot acceptance checks: recovery path available, enrollment verified,
  fresh login succeeds, and old Authy entry retained until success. Seed rotation
  can invalidate that entry immediately; independent recovery is required. Keep account
  identity and recovery material outside this workspace.

Likely blockers: missing CLI installation, locked or unintegrated desktop app,
clock drift, uncertain recovery access, or a proprietary Authy integration.
Report blockers without installing packages or changing MFA as an automatic fix.

Stop when the model, repository policy, current references, preflight evidence, and
pilot checklist are recorded. Actual enrollment is T-AUTH-003 and requires its own
explicit authorization. No account is marked migrated by completing this checklist.
