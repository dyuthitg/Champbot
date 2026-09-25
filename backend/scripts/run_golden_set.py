"""
Runs the REAL copywriter (src/outreach/copy.py, real OpenRouter call) against
all 30 golden-set cases and grades every result with a deterministic 0-3
scorer, so the number is reproducible: same code + same candidate text always
lands on the same score, and anyone can rerun this file and get the same
output the memo quotes.

    python scripts/run_golden_set.py baseline    # before the prompt change
    python scripts/run_golden_set.py after        # after it

Writes docs/golden_set/<label>_run.csv (one row per case) and prints the
aggregate numbers the before/after memo is built from.

Scoring, operationalizing RUBRIC.md's anchors as concrete rules:

  0  - SKIP case that got a comment at all; OR failed src/outreach/quality.py's
       gate outright (a blocker, e.g. TEMPLATE3); OR a tone_risk case whose
       comment uses celebratory language ("congrats", "exciting!", etc.) when
       the post explicitly called for restraint (bridge round, layoff, sunset).
  3   - passed the gate AND mentions this case's "hook" -- a hand-picked word
        or phrase that only shows up if the comment engaged with the one
        distinctive detail in THIS post, not the general topic.
  2   - passed the gate, has a personalization signal (quality.py's own
        first-name/company/headline/post-word check), but missed the hook.
  1   - passed the gate but shows no personalization signal at all: could
        have been posted under a different name with zero changes.

This is a proxy, not a perfect model of human judgment -- said plainly in the
memo. A single hand-picked hook word can miss a comment that engaged with the
post in a different, equally specific way. It's reproducible and auditable
(every hook is sitting in the CSV, not hidden in someone's head), which is
what "anyone can rerun this and land on the same figures" actually requires.
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# docs/ stayed at the repo root when this project split into frontend/ and
# backend/ (2026-09-16); REPO here is backend/, one level below that.
ROOT = REPO.parent
GOLDEN_CSV = ROOT / "docs" / "golden_set" / "golden_set.csv"
OUT_DIR = ROOT / "docs" / "golden_set"

_CELEBRATORY = [
    "congrat", "exciting", "amazing", "awesome", "thrilled for you",
    "so happy for you", "great news", "well deserved", "fantastic news",
]


def _load_env() -> None:
    env_path = REPO / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def score_case(row: dict, candidate_text: str, report) -> tuple[int, str]:
    text = (candidate_text or "").strip()
    low = text.lower()

    if row["skip"] == "1":
        if text:
            return 0, "commented on a SKIP case (gold standard: no comment at all)"
        return 3, "correctly produced no comment"

    if not report.passed:
        reason = "; ".join(report.blockers) or "failed the quality gate"
        return 0, f"blocked by the quality gate: {reason}"

    if row["tone_risk"] == "1" and any(w in low for w in _CELEBRATORY):
        return 0, "celebratory/congratulatory language on a case that needed restraint"

    hooks = [h for h in row["hooks"].split("|") if h]
    hit = [h for h in hooks if h in low]
    if hit:
        return 3, f"referenced the case's specific hook: {hit}"

    if report.stats.get("personalization_signals"):
        return 2, "passed the gate, some personalization, but missed this case's specific hook"

    return 1, "passed the gate but generic -- no personalization signal at all"


async def run(label: str) -> None:
    _load_env()

    from src.outreach import copy as copywriter
    from src.infrastructure.llm.provider import LLMProvider, OpenRouterConfig

    config = OpenRouterConfig.from_env()
    if not config.api_key:
        print("WARNING: no OPENROUTER_API_KEY -- this will run the template fallback, "
              "not the real model. The before/after comparison needs the real model on "
              "both sides or it isn't measuring the prompt change.")
    provider = LLMProvider(config) if config.api_key else None

    account = SimpleNamespace(display_name="Demo Account", headline="Founder at Champions Ranch")
    icp = SimpleNamespace(value_proposition="I help B2B SaaS teams fix activation drop-off.", instructions=None)

    with open(GOLDEN_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    results = []
    for row in rows:
        target = SimpleNamespace(
            full_name=row["full_name"],
            first_name=row["full_name"].split()[0] if row["full_name"] else None,
            title=row["title"] or None,
            company=row["company"] or None,
            industry=row["industry"] or None,
            headline=None,
            context={"post_text": row["source_post"]},
        )
        draft = await copywriter.draft("comment", target, account, icp, provider=provider, org_id="golden-set")
        score, reason = score_case(row, draft.text, draft.quality)
        results.append(
            {
                "id": row["id"],
                "category": row["category"],
                "skip": row["skip"],
                "candidate_text": draft.text,
                "generated_by": draft.generated_by,
                "quality_score": draft.quality.score,
                "quality_flags": ";".join(draft.quality.flag_codes),
                "rubric_score": score,
                "rubric_reason": reason,
            }
        )
        print(f"  {row['id']} [{row['category']:20s}] rubric={score}  ({reason})")

    out_path = OUT_DIR / f"{label}_run.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    scores = [r["rubric_score"] for r in results]
    avg = sum(scores) / len(scores)
    zeros = sum(1 for s in scores if s == 0)
    generic_phrase_failures = sum(
        1 for r in results if "R4" in r["quality_flags"].split(";") or "TEMPLATE3" in r["quality_flags"].split(";")
    )

    print()
    print(f"[{label}] average rubric score: {avg:.2f} / 3   ({len(results)} cases)")
    print(f"[{label}] score-of-0 count: {zeros}")
    print(f"[{label}] generic-phrase failures (R4 or TEMPLATE3 flag): {generic_phrase_failures}")
    print(f"[{label}] wrote {out_path}")


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    asyncio.run(run(label))
