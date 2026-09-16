"""
Audit scorer: read audit_log.csv, score every generated comment against a
failure taxonomy, and write a scored CSV + a summary report.

    python scripts/score_audit.py
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IN_CSV = os.path.join(HERE, "audit_log.csv")
OUT_CSV = os.path.join(HERE, "audit_log_scored.csv")
REPORT = os.path.join(HERE, "audit_report.md")

# --- Taxonomy ---------------------------------------------------------------
# Phrase-level clichés are noise. The failure mode that actually matters for a
# bot at scale is STRUCTURAL: does the comment say something only this post
# could prompt, or is it the same 3-beat template (validate -> restate the
# thesis -> "have you found any specific strategies?") stamped on 58 posts?

# Openers that validate before saying anything. One is fine; the pattern is not.
VALIDATE_OPENERS = ["you raise a good point", "you make a good point",
                    "you make a great point", "you make a solid point",
                    "that's a solid", "that is a solid", "great point",
                    "good point", "you nailed it", "you've nailed it",
                    "spot on", "absolutely agree", "well said", "it's interesting",
                    "it is interesting", "interesting approach", "interesting results",
                    "that's a pivotal", "that's a significant"]

# The tell-tale low-effort question the model leans on to feign engagement.
STRATEGY_QUESTION = ["have you found", "what strategies have you",
                     "any specific strategies", "what specific strategies",
                     "have you seen any specific", "have you noticed any",
                     "did you notice any", "what strategies"]

FLATTERY = ["nailed it", "spot on", "brilliant", "love this", "great post"]


def _ends_with_generic_strategy_q(low: str) -> bool:
    return any(p in low for p in STRATEGY_QUESTION)


def detect(text: str, target_post: str = "") -> list:
    t = (text or "").strip()
    low = t.lower()
    tags = []
    words = t.split()

    if len(t) > 300:
        tags.append("too_long")
    if len(words) < 5:
        tags.append("too_thin")

    opens_with_validation = any(low.startswith(p) or f" {p}" in low[:40]
                                for p in VALIDATE_OPENERS)
    strategy_q = _ends_with_generic_strategy_q(low)

    if opens_with_validation:
        tags.append("validation_opener")
    if strategy_q:
        tags.append("formulaic_strategy_question")
    if opens_with_validation and strategy_q:
        # The full 3-beat bot template. This is the damning one.
        tags.append("template_3beat")
    if any(p in low for p in FLATTERY):
        tags.append("sycophancy")
    if "!" in t:
        tags.append("exclamation_hype")

    # Specificity: does the comment reuse a distinctive content word from the
    # post (not just generic business vocab)? If not, it's interchangeable.
    if target_post:
        stop = {"activation", "retention", "onboarding", "growth", "strategies",
                "specific", "found", "teams", "users", "really", "interesting",
                "metrics", "engagement", "product", "marketing"}
        post_words = {w.strip(".,!?'\"-").lower() for w in target_post.split()
                      if len(w) >= 6}
        distinctive = post_words - stop
        hit = any(w in low for w in distinctive)
        if not hit:
            tags.append("no_specific_detail")

    return tags or ["good"]


def grade(tags: list) -> str:
    if "good" in tags:
        return "good"
    s = set(tags)
    # The 3-beat template with no specific detail is a hard fail: at scale this
    # is unmistakably a bot.
    if "template_3beat" in s and "no_specific_detail" in s:
        return "fail"
    if "no_specific_detail" in s and "validation_opener" in s:
        return "fail"
    if "template_3beat" in s or "no_specific_detail" in s:
        return "weak"
    if s & {"too_thin", "sycophancy", "exclamation_hype"}:
        return "weak"
    return "weak"


def main() -> None:
    with open(IN_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    scored = []
    tag_counts = Counter()
    for r in rows:
        text = r["draft_text"]
        post = r.get("post_text", "")  # populated if the export included it
        tags = detect(text, post)
        g = grade(tags)
        for t in tags:
            tag_counts[t] += 1
        r["tags"] = ";".join(tags)
        r["grade"] = g
        scored.append(r)

    # score 0-100: good=90, weak=60, fail=25, minus a bit per extra tag
    def score(r):
        base = {"good": 90, "weak": 60, "fail": 25}[r["grade"]]
        extra = max(0, len(r["tags"].split(";")) - 1) * 5
        return max(0, base - extra)

    for r in scored:
        r["audit_score"] = score(r)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(scored[0].keys()))
        w.writeheader()
        w.writerows(scored)

    good = [r for r in scored if r["grade"] == "good"]
    fail = [r for r in scored if r["grade"] == "fail"]
    ranked = sorted(scored, key=lambda r: r["audit_score"])

    lines = ["# Comment Audit — Failure Taxonomy & Scores", ""]
    lines.append(f"Total comments scored: **{len(scored)}**")
    lines.append(f"- Good: **{len(good)}**")
    lines.append(f"- Weak: **{len(scored) - len(good) - len(fail)}**")
    lines.append(f"- Fail: **{len(fail)}**")
    lines.append("")
    lines.append("## Taxonomy (tag frequency)")
    for tag, n in tag_counts.most_common():
        lines.append(f"- `{tag}`: {n}")
    lines.append("")
    lines.append("## Three worst (verbatim)")
    for r in ranked[:3]:
        lines.append(f"- **score {r['audit_score']}** [{r['tags']}]\n  > {r['draft_text']}")
    lines.append("")
    lines.append("## Three best (verbatim)")
    for r in sorted(scored, key=lambda r: -r["audit_score"])[:3]:
        lines.append(f"- **score {r['audit_score']}** [{r['tags']}]\n  > {r['draft_text']}")

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Scored {len(scored)} -> {OUT_CSV}")
    print(f"Report -> {REPORT}")
    print(f"good={len(good)} weak={len(scored)-len(good)-len(fail)} fail={len(fail)}")
    print("tags:", dict(tag_counts))


if __name__ == "__main__":
    main()
