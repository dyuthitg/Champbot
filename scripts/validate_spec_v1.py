"""
Mechanically grades a stratified sample of 10 real audit comments against the
literal, testable rules in COMMENT_QUALITY_SPEC_V1.md, and checks whether the
automatic PASS/REJECT call agrees with the human grade already assigned in
audit_log_scored.csv (BOT_OUTPUT_AUDIT_V1.md).

This IS the acceptance test the spec proposes ("hand it to someone who has
never seen the product") — run mechanically instead of by a person, which is
a strictly harder bar since a machine has zero context to fall back on.

Run: python scripts/validate_spec_v1.py
"""

import csv
import re

# --- R4: literal banned phrases --------------------------------------------
# Existing list (src/outreach/quality.py _TIRED_PHRASES) plus every phrase
# that actually recurred 3+ times in audit_log_scored.csv, plus the seed
# phrases from the brief (thanks for sharing / great insights / spot on).
BANNED_PHRASES = [
    # brief's seed list
    "thanks for sharing", "great insights", "spot on",
    # from the audit data — restricted to phrases that map to a tag the human
    # audit actually named (validation_opener / sycophancy in BOT_OUTPUT_AUDIT_V1.md).
    # "it's interesting how" / "i've seen teams" recurred often too but were never
    # flagged by the human grader as a violation on their own — one "good"-graded
    # comment uses "it's interesting how" outright, so v1 leaves them off the
    # automatic-reject list rather than hard-reject on frequency alone.
    "you make a solid point", "you make a great point", "you raise a good point",
    "you raise a crucial point", "you're spot on", "you've nailed it", "you nailed it",
    "absolutely agree", "that's a solid approach",
    # carried over from the existing gate (still valid)
    "i hope this message finds you well", "quick question", "circle back",
    "touch base", "pick your brain", "synergy", "game-changer", "game changer",
]

# --- R5: the formulaic closing-question template ---------------------------
# The audit found ~15 literal variants of ONE template. Banning strings alone
# is whack-a-mole — this bans the shape. First cut used a strict positional
# regex ("have you found ... strategies") and missed the reordered form "what
# strategies have you found" — same template, clause order flipped. Rewritten
# order-independent: the "found" + "you" pair close together, a topic noun
# ANYWHERE in the sentence, and the sentence ends in a question mark.
_VERB = r"(?:found|find|finds|noticed|seen|tried)"
_PRONOUN = r"(?:you|you've|you'd|your)"
_FOUND_YOU_RE = re.compile(
    rf"\b{_PRONOUN}\b[\w\s']{{0,20}}\b{_VERB}\b|\b{_VERB}\b[\w\s']{{0,20}}\b{_PRONOUN}\b",
    re.I,
)
_TOPIC_NOUN_RE = re.compile(r"\b(strateg\w*|approach\w*|tactic\w*|framework\w*|trend\w*|metric\w*)\b", re.I)


def matches_formulaic_question(text: str) -> bool:
    for sentence in SENTENCE_SPLIT_RE.findall(text):
        s = sentence.strip()
        if s.endswith("?") and _FOUND_YOU_RE.search(s) and _TOPIC_NOUN_RE.search(s):
            return True
    return False

# --- R3: specificity stoplist (closes the exact bug from the audit) --------
GENERIC_WORDS = {
    "activation", "retention", "onboarding", "engagement", "strategies",
    "adoption", "conversion", "growth", "strategy", "platform", "product",
    "customer", "customers", "company", "business", "software",
    "feature", "features", "process", "approach", "important", "focusing",
    "improve", "effective", "specific", "particular",
}
# NOTE: "revenue" was in an earlier draft of this list and got pulled — it
# wrongly rejected a "good"-graded comment built entirely around "net revenue
# retention," the post's actual subject. Not in the original quality.py
# stoplist either. Lesson: extend the stoplist from repeated GENERIC filler,
# not from any word that happens to be long.

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]")
SENTENCE_SPLIT_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
# 280, not a guessed "3 lines ~ 220": real audit data shows NO length/grade
# correlation (good comments run 161-258 chars, fail comments 143-269) — so
# this is a sanity ceiling against outliers, not an active discriminator.
MAX_CHARS = 280


def count_sentences(text: str) -> int:
    return len([s for s in SENTENCE_SPLIT_RE.findall(text) if s.strip()])


def has_specific_reference(comment: str, post_text: str) -> bool:
    comment_l = comment.lower()
    words = re.findall(r"\b[a-z]{6,}\b", post_text.lower())
    return any(w in comment_l and w not in GENERIC_WORDS for w in words)


def grade(comment: str, post_text: str):
    """Returns (verdict, reasons) — verdict is PASS or REJECT."""
    reasons = []

    n_sent = count_sentences(comment)
    if not (1 <= n_sent <= 3):
        reasons.append(f"R1 sentence count = {n_sent} (must be 1-3)")

    if len(comment) > MAX_CHARS:
        reasons.append(f"R2 length = {len(comment)} chars (max {MAX_CHARS})")

    if not has_specific_reference(comment, post_text):
        reasons.append("R3 no non-generic word from the source post appears in the comment")

    hit = next((p for p in BANNED_PHRASES if p in comment.lower()), None)
    if hit:
        reasons.append(f"R4 banned phrase: '{hit}'")

    if matches_formulaic_question(comment):
        reasons.append("R5 matches the formulaic closing-question template")

    if EMOJI_RE.search(comment):
        reasons.append("R6 contains emoji")

    if comment.count("!") > 1:
        reasons.append("R7 more than one exclamation mark")

    return ("REJECT" if reasons else "PASS"), reasons


def main():
    with open("audit_log_scored.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["draft_text"] = r["draft_text"].replace("�", "'")

    by_grade = {"good": [], "weak": [], "fail": []}
    for r in rows:
        by_grade[r["grade"]].append(r)

    # Stratified, deterministic sample: 3 good, 4 weak, 3 fail = 10.
    sample = by_grade["good"][:3] + by_grade["weak"][:4] + by_grade["fail"][:3]

    print(f"{'#':<3}{'human grade':<12}{'mechanical':<10}{'agree?':<8}reasons")
    print("-" * 100)
    agree = 0
    for i, r in enumerate(sample, 1):
        verdict, reasons = grade(r["draft_text"], r["post_text"])
        human_bad = r["grade"] in ("weak", "fail")
        mech_bad = verdict == "REJECT"
        matches = human_bad == mech_bad
        agree += matches
        print(f"{i:<3}{r['grade']:<12}{verdict:<10}{'yes' if matches else 'NO':<8}{'; '.join(reasons) or '(none)'}")

    print("-" * 100)
    print(f"Agreement with human grade: {agree}/10")


if __name__ == "__main__":
    main()
