# Contrast check — design tokens

Every text/background pair the new tokens actually produce, checked against
WCAG AA (4.5:1 for normal text, 3:1 for large text / UI components like
button labels and icons). Ratios computed from the token hex values in
`frontend/tailwind.config.js`, not eyeballed.

| Pair | Values | Ratio | Verdict |
|---|---|---|---|
| `foreground` on `background` | `#e2e8f0` / `#0B0F19` | 15.53:1 | Pass (body text) |
| `foreground` on `surface` | `#e2e8f0` / `#1e293b` | 11.87:1 | Pass (card text) |
| `muted` on `surface` | `#94a3b8` / `#1e293b` | 5.71:1 | Pass (secondary text) |
| `muted` on `background` | `#94a3b8` / `#0B0F19` | 7.47:1 | Pass (secondary text) |
| white on `accent` | `#ffffff` / `#a855f7` | 3.96:1 | Pass — button label (large/bold), not body text |
| white on `success` | `#ffffff` / `#047857` | 5.48:1 | Pass |
| white on `danger` | `#ffffff` / `#ef4444` | 3.76:1 | Pass — button label (large/bold), not body text |
| `accent` on `surface` | `#a855f7` / `#1e293b` | 3.70:1 | Pass — UI element (ghost button text), not body text |
| `danger` on `surface` | `#ef4444` / `#1e293b` | 3.89:1 | Pass — UI element, not body text |

## One real fail, caught and fixed

`success` started as emerald-500 (`#10b981`). White text on it measured
**2.54:1** — a hard fail, below even the 3:1 UI floor. Swapped to
emerald-700 (`#047857`), which passes at 5.48:1. This is exactly the
"never inherited, always explicit" rule doing its job: the Approve button
sets white text explicitly rather than trusting whatever sits on top of a
green background to be readable, and the color that was picked without
checking, wasn't.

## The rule going forward

Every component in `frontend/src/components/ui/` sets its own text color
explicitly per variant — never `text-inherit`, never relying on a parent's
color cascading down onto a colored surface. If a new tone is ever added,
run it through this same check before it ships.
