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
| white on `warn` | `#ffffff` / `#f59e0b` | 2.15:1 | **Never do this** — `warn` is a text colour only, never a fill under white |
| `accent` on `surface` | `#a855f7` / `#1e293b` | 3.70:1 | Pass — UI element (ghost button text), not body text |
| `danger` on `surface` | `#ef4444` / `#1e293b` | 3.89:1 | Pass — UI element, not body text |

## Added 2026-09-04 — the guardrail chips

The queue now labels every rule a draft broke, so severity is carried by a
chip: coloured text on a 15% tint of its own colour over `surface`. Ratios
below are measured against that **composited** background (e.g. `danger/15`
over `surface` resolves to `#3d2d3c`), not against `surface` itself — a tint
is what the text actually sits on.

| Pair | Values | Ratio | Verdict |
|---|---|---|---|
| `warn` on `background` | `#f59e0b` / `#0B0F19` | 8.92:1 | Pass |
| `warn` on `surface` | `#f59e0b` / `#1e293b` | 6.81:1 | Pass |
| `warn` on `warn/15` chip | `#f59e0b` / `#3e3b34` | 5.20:1 | Pass |
| `danger-fg` on `danger/15` chip | `#f87171` / `#3d2d3c` | 4.63:1 | Pass |
| `success-fg` on `success/15` chip | `#34d399` / `#1a353f` | 6.72:1 | Pass |
| `danger-fg` on `surface` | `#f87171` / `#1e293b` | 5.29:1 | Pass |
| `success-fg` on `surface` | `#34d399` / `#1e293b` | 7.61:1 | Pass |

### Two more real fails, caught the same way

Writing the chips surfaced a bug the token set had been carrying quietly:
`success` and `danger` were only ever checked as *fills*, with white text on
top. Used as **text** on a dark surface they measure

- `success` `#047857` on a `success/15` chip — **2.36:1**
- `danger` `#ef4444` on a `danger/15` chip — **3.40:1**

Both fail AA, and one fails the 3:1 UI floor as well. A fill dark enough to
carry white text is by definition too dark to *be* text on a dark ground —
the two jobs need two values.

So `success` and `danger` each became a pair: the fill keeps the same hex
(`bg-success`, `bg-danger`, borders and tints are all unchanged), and a new
`-fg` value carries the same meaning as text — emerald-400 `#34d399` and
red-400 `#f87171`. Every place that wrote one of those colours as text now
uses `-fg`: the chips, the live length counter, the Never-contact button
label, and the relevance badge.

`warn` `#f59e0b` was added at the same time, for the state between "fine"
and "cannot be sent" — a comment nearing its length target. It passes as
text everywhere it is used, so it needs no second value.

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
