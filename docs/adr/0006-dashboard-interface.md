# ADR 0006: A persistent terminal dashboard

- Status: Accepted by operator request, 2026-10-12
- Supersedes: sequential scope forms in ADR 0004; retains standard-library curses

## Context

The original menu replaced the entire screen for every input and response.
The operator requested an interface closer to btop and htop, with stronger visual
hierarchy and navigation. Empty forms were easily mistaken for continuation screens.

## Decision

Provide bordered navigation and workspace panels, a persistent backend indicator,
highlighted actions, contextual help and a keyboard footer. Use color where
available and a monochrome fallback. Present all required scope fields together;
validate empty or incomplete fields in place before dispatch. Retain number-key
shortcuts and add arrow/j/k navigation, Tab field navigation and backend selection.

Keep scope hidden, ephemeral and explicitly entered for each operation. Show only
truthful capability observations; no dashboard panel infers migration completion
or account authorization. Do not poll vaults or generate OTPs in the background.

## Consequences

The interface remains dependency-free and usable at 60 by 18, with the full layout
at 80 by 24 and above. Resize and unavailable-color paths require tests. Codes and
private forms still require deliberate dismissal and are never saved by the UI.
No visual resemblance implies integration with or copied source from btop/htop.
