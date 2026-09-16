# Brand voice profiles

This folder is how a brand's voice gets defined. It's a folder of files, not
a screen in the code — a marketer can add, tweak, or retire a brand by
editing a file here and saving it. No engineer, no deploy, no pull request.

## Adding a new brand

1. Copy `_template.yaml`, rename it to your brand (e.g. `acme-corp.yaml`).
2. Open it and fill in the blanks. Every line explains itself.
3. Save it here. It shows up in the "Brand voice" picker next to any target
   profile the next time that screen loads.

That's the entire process. `lake-b2b.yaml` and `loopwork.yaml` in this same
folder are two real, finished examples — one formal enterprise brand, one
casual startup brand — deliberately as different as two brands can be, to
show the same six fields cover both.

## What each field actually controls

| Field | What it does |
|---|---|
| `id` | The internal name. Must match the filename. Not shown to anyone. |
| `brand_name` | The name people see in the dropdown. |
| `formality` | `casual`, `conversational`, or `formal` — the overall register of the writing. |
| `max_sentences` | A hard cap. The writer will not go over this, ever. |
| `emoji_frequency` | `never`, `rare`, or `occasional`. |
| `banned_phrases` | Words this brand should never say. This list is on top of the product's own baked-in banned list (things like "I hope this finds you well") — you're only adding brand-specific ones. |
| `preferred_phrases` | Optional. Words that sound like this brand, used only when they fit — never stuffed in. |
| `tone_words` | Optional. A handful of adjectives. Short, but they earn their place. |
| `cta_style` | Optional. Whether a comment can end with a question, and how direct it can be. |
| `signoff` | Optional. Whether to use the person's first name. |
| `notes` | Optional. Anything else, your own words. |
| `example_comments` | At least 2 real examples written the way this brand actually talks. **This is the field that matters most** — the writer leans on these harder than any of the settings above. Vague settings with two great examples beat perfect settings with lazy ones. |

## What this does *not* control

Brand voice is tone — how something is said. It never overrides the
product's safety rules: never inventing a fact, never a link, never asking
for a meeting, never a leaked template placeholder. Those apply to every
brand, no exceptions, and nothing in this file can turn them off.

## Where it's used

Once a profile exists here, open a target profile (ICP) in the Targeting
screen and pick it from the "Brand voice" dropdown. Every comment drafted
for that target profile then writes in that brand's voice. Leaving it on
"Default" uses the product's plain, brand-neutral voice — the same one
every account got before this existed.

## If a file doesn't show up

The most common reason is a typo the schema catches: a missing required
field, an `id` that doesn't match the filename, or fewer than 2 example
comments. Nothing crashes — a broken file is just skipped, and the account
falls back to the default voice, so a bad edit here can never take outreach
down. Check the field table above against your file; every required field
is marked in `_template.yaml` and in `schema.json` if you want the exact
technical rules.
