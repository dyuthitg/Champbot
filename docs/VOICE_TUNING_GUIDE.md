# Voice-tuning guide

Two different kinds of change live under two different processes. Knowing
which one you need is the first decision:

| You want to... | Change a **file** (no deploy) | Change **code** (needs a deploy) |
|---|---|---|
| Give one brand its own tone, examples, or a brand-specific word to avoid | ✅ §1 | |
| Add a word/phrase every brand should always avoid, or fix how a shared rule scores | | ✅ §2 |

If you're not sure which one you need: if the change should only affect
comments drafted for one specific brand's target profiles, it's §1. If it
should affect every comment the system ever writes, it's §2.

---

## 1. Per-brand voice — add a brand profile, or change one (no deploy)

This is a marketer's job, not an engineer's. It's a folder of YAML files —
`backend/config/brand_voices/` — read fresh every time a file's timestamp
changes, so saving the file is the entire deploy.

### Add a new brand

1. Copy `backend/config/brand_voices/_template.yaml`, rename it to your
   brand, e.g. `acme-corp.yaml`.
2. Set `id:` inside to match the filename exactly (`acme-corp`, no `.yaml`)
   — this is the one thing that has to line up, and it's the #1 reason a new
   file doesn't show up (see "If it doesn't show up" below).
3. Fill in the fields marked REQUIRED: `brand_name`, `formality`,
   `max_sentences`, `emoji_frequency`, `banned_phrases`, and at least 2
   `example_comments`. Everything else is optional — see the field table in
   `backend/config/brand_voices/README.md` for what each one does.
4. Spend real effort on `example_comments`. The copywriter leans on these
   harder than any of the settings above them — two genuinely on-voice
   examples beat a perfectly filled-in settings block with lazy ones.
5. Save the file in that same folder. It appears in the "Brand voice"
   dropdown on the Targeting screen, next to any target profile, the next
   time that screen loads. No restart, no deploy, no PR required.

`lake-b2b.yaml` and `loopwork.yaml` in the same folder are two finished, real
examples — one formal enterprise brand, one casual startup brand — built
deliberately as different as two brands can be to prove the same six fields
stretch to cover both. Copy whichever one is closer to what you're building
before you copy `_template.yaml` from scratch.

### Add a brand-specific banned phrase

Add it to that brand's `banned_phrases:` list in its own YAML file. This is
**on top of** the product-wide list (§2) — you're only adding words specific
to this brand; you don't need to (and shouldn't) re-list the global ones.

### Change an existing brand's voice

Open its file, edit the field, save. `formality`, `max_sentences`,
`cta_style`, `tone_words`, and the examples are the ones that actually move
the output — tweak those first if a brand's comments don't sound right, before
assuming the problem is upstream in the shared writer.

### If it doesn't show up

A broken file is skipped silently and that ICP falls back to the default
voice — nothing crashes, but nothing you wrote applies either. In order,
check:

1. Does `id:` match the filename exactly (no `.yaml`, correct case)?
2. Are there at least 2 entries under `example_comments`, each with both
   `post_context` and `comment`?
3. Is every REQUIRED field in `_template.yaml` actually filled in?
4. Does `formality`, `emoji_frequency`, `cta_style`, or `signoff` use one of
   the exact allowed values (see the template's comments)? A typo here is
   the most common miss.

`backend/config/brand_voices/schema.json` has the exact technical rules if
you want to check a file against it directly.

### What this can never change

Brand voice governs tone only. It cannot turn off the shared safety rules —
no invented facts, no links, no pitching, no leaked placeholders. Those are
enforced by the quality gate (§2) on every brand's output, no exceptions, and
nothing in a brand voice file can override them.

---

## 2. Shared rules — add a global banned phrase, or change a rule (deploy required)

Every draft, regardless of brand, passes through one shared gate:
`backend/src/outreach/quality.py`. This is Python, not config — a change here
needs a code review and a deploy, same as any other product change.

### Add a phrase every brand should avoid

Add it to `_TIRED_PHRASES` (worn-out outreach phrasing — deducts from score,
doesn't block) or `_VALIDATION_OPENER_PHRASES` (openers that count toward the
`TEMPLATE3` blocker when combined with a formulaic closing question) near the
top of `quality.py`. Lower-case, no punctuation weirdness — matching is
case-insensitive but literal.

Before adding one, check `COMMENT_QUALITY_SPEC_V1.md`'s R4 list first — if
the phrase is already named there, it may just not be wired into the code
yet (`COMMENT_RULES_ENFORCEMENT_GAP.md` tracks exactly this kind of gap, and
it's bitten this project before: an 11-phrase gap between the written spec
and the enforced list sat for ten days once). Wiring an already-spec'd phrase
in is a smaller, safer change than inventing a new one.

### Change how a rule scores or blocks

Each rule is named once in the `RULES` table near the top of `quality.py` —
a `code`, an operator-facing `label`, and (where one exists) the spec section
it comes from. That table is what the queue's chips and filters read from,
so a rule is called the same thing everywhere. To change a rule:

1. Find its `code` in `RULES` and its check further down in `check_copy()`.
2. Change the regex, phrase list, or threshold. Leave the `code` alone if
   the rule's meaning hasn't fundamentally changed — the queue's filters and
   any historical reports key off it.
3. Decide the severity deliberately: `blocker` (can never be approved until
   rewritten), `warning` (deducts from score, reviewer decides), or
   `advisory` (shown, never blocks or scores). Loosening a `blocker` to a
   `warning` is a real policy call, not a bug fix — say so in the PR, the way
   `TEMPLATE3` was promoted to a blocker after the first live audit showed
   `R4`+`R5` alone weren't stopping the exact pattern they were meant to.
4. Add a test in `tests/` with the real string that motivated the change —
   every existing rule in this file was tightened because a real draft got
   through it, not because it was reasoned about in the abstract. Keep that
   habit; it's why the comments throughout `quality.py` cite the specific
   run that found each gap.
5. Run the golden set before and after (see
   `docs/QUALITY_MEASUREMENT_METHOD.md`) if the change is anything more than
   adding one phrase to a list — a rule tightened to catch one bad case can
   also catch good ones you didn't test against.

### Where the two lists can drift, and why it matters

`COMMENT_QUALITY_SPEC_V1.md` is the written spec; `quality.py` is what's
actually enforced. They are not automatically the same file, and this project
has already been burned once by that gap being invisible for ten days. If you
change one, check the other — and if you're intentionally leaving a gap (the
way `R1`, `R5`, and parts of `R6`/`R7` are currently advisory-only, pending a
shared decision on tightening them), say so in the code comment the way the
existing gaps are documented, not silently.
