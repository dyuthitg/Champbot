"""
Turn a day of real review into evidence.

The Sep 16-17 go-live commitment is "a real person uses it for a full day, for
real." The risk with a day like that is that it produces a feeling — "it seemed
fine" — and a feeling is not something the Sep 18 go/no-go can be decided on.

Everything needed is already recorded: every approve and every skip writes a
ledger row (``AccountActivity``) with a timestamp and, for a skip, the reason
the reviewer typed. This reads that trail and answers the four questions the
go/no-go actually turns on:

1. How much did they get through, and how fast?
2. What did they refuse, and in their own words, why?
3. **Do the guardrail flags predict what a human rejects?** This is the one
   that matters. If flagged drafts get approved at the same rate as clean ones,
   the flags are decoration.
4. What did the system do to them — blocked drafts, dead ends, errors.

    python scripts/session_report.py --db staging_run/staging.db
    python scripts/session_report.py --db prod.db --since 2026-09-16 --until 2026-09-18

Writes SESSION_REPORT.md next to wherever it is pointed, and prints a summary.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# A gap longer than this between two decisions is a break, not thinking time.
# Without it one lunch hour makes the median look like the reviewer agonised
# over every card.
BREAK_SECONDS = 300


def _parse_day(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def load(db_path: str, since: datetime | None, until: datetime | None) -> dict:
    """Read the review trail straight out of SQLite — no server needed."""
    import sqlite3

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    activity = [
        dict(r)
        for r in con.execute(
            "select action, status, detail, target_id, created_at "
            "from account_activity where action in ('approve','reject') "
            "order by created_at asc"
        )
    ]
    for row in activity:
        row["detail"] = json.loads(row["detail"]) if row["detail"] else {}
        row["at"] = _to_dt(row["created_at"])

    if since:
        activity = [r for r in activity if r["at"] and r["at"] >= since]
    if until:
        activity = [r for r in activity if r["at"] and r["at"] < until]

    # Keyed without dashes: the ledger records str(uuid), while SQLite stores
    # the column as 32 hex characters. Matching them naively finds nothing and
    # the flag table comes out empty with no error.
    suggestions = {
        _key(r["id"]): dict(r)
        for r in con.execute(
            "select s.id, s.action, s.status, s.draft_text, s.final_text, "
            "s.quality_score, s.relevance_score, t.full_name, t.headline, "
            "t.title, t.company, t.context "
            "from outreach_suggestions s "
            "left join outreach_targets t on t.id = s.target_id"
        )
    }
    blocked = [s for s in suggestions.values() if s["status"] == "blocked"]
    con.close()
    return {"activity": activity, "suggestions": suggestions, "blocked": blocked}


def _key(value) -> str:
    """UUIDs compare as bare hex; the ledger and the row disagree on dashes."""
    return str(value or "").replace("-", "").lower()


def _to_dt(raw) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def flags_for(suggestion: dict) -> list:
    """Re-run the gate over the reviewed text to get its named rules."""
    from src.outreach.quality import check_copy

    text = suggestion.get("final_text") or suggestion.get("draft_text")
    if not text:
        return []
    context = suggestion.get("context")
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except (TypeError, ValueError):
            context = {}
    target = type(
        "T",
        (),
        {
            "first_name": (suggestion.get("full_name") or " ").split()[0],
            "full_name": suggestion.get("full_name"),
            "title": suggestion.get("title"),
            "company": suggestion.get("company"),
            "headline": suggestion.get("headline"),
            "industry": None,
            "context": context or {},
        },
    )()
    action = suggestion.get("action") or "comment"
    if action not in ("connect", "message", "comment"):
        return []
    return check_copy(text, action, target).flags


def analyse(data: dict) -> dict:
    activity = data["activity"]
    suggestions = data["suggestions"]

    decisions = []
    previous = None
    for row in activity:
        sid = _key((row["detail"] or {}).get("suggestion_id"))
        gap = None
        if previous and row["at"] and previous["at"]:
            seconds = (row["at"] - previous["at"]).total_seconds()
            if 0 <= seconds <= BREAK_SECONDS:
                gap = seconds
        decisions.append(
            {
                "kind": row["action"],
                "suppressed": bool((row["detail"] or {}).get("suppress_target")),
                "reason": (row["detail"] or {}).get("reason"),
                "at": row["at"],
                "seconds": gap,
                "suggestion": suggestions.get(sid),
            }
        )
        previous = row

    approvals = [d for d in decisions if d["kind"] == "approve"]
    rejects = [d for d in decisions if d["kind"] == "reject"]
    never = [d for d in rejects if d["suppressed"]]
    gaps = [d["seconds"] for d in decisions if d["seconds"] is not None]

    # The question the whole guardrail effort stands on.
    by_flag: dict = defaultdict(lambda: {"approved": 0, "skipped": 0, "label": ""})
    clean = {"approved": 0, "skipped": 0}
    for decision in decisions:
        suggestion = decision["suggestion"]
        if not suggestion:
            continue
        codes = flags_for(suggestion)
        bucket = "approved" if decision["kind"] == "approve" else "skipped"
        if not codes:
            clean[bucket] += 1
            continue
        for flag in {(f.code, f.label) for f in codes}:
            by_flag[flag[0]][bucket] += 1
            by_flag[flag[0]]["label"] = flag[1]

    return {
        "decisions": decisions,
        "approvals": approvals,
        "rejects": rejects,
        "never": never,
        "gaps": gaps,
        "by_flag": dict(by_flag),
        "clean": clean,
        "reasons": Counter(
            (d["reason"] or "").strip().lower() for d in rejects if d["reason"]
        ),
        "blocked": data["blocked"],
    }


def render(result: dict, db_path: str) -> str:
    decisions = result["decisions"]
    gaps = result["gaps"]
    total = len(decisions)
    approved = len(result["approvals"])
    skipped = len(result["rejects"])

    lines = [
        "# Review session report",
        "",
        f"Source: `{db_path}` · generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        "",
        "## How much got through",
        "",
        f"- **{total}** decisions",
        f"- **{approved}** approved ({_pct(approved, total)}), "
        f"**{skipped}** skipped ({_pct(skipped, total)}), "
        f"of which **{len(result['never'])}** were 'never contact'",
    ]
    if gaps:
        lines += [
            f"- Median **{statistics.median(gaps):.0f}s** per decision, "
            f"slowest tenth over **{_p90(gaps):.0f}s**",
            f"- Sustained pace: about **{3600 / max(statistics.median(gaps), 1):.0f} decisions/hour**",
        ]
    else:
        lines.append("- Not enough consecutive decisions to measure a pace")

    lines += [
        "",
        "## Do the flags predict what a human rejects?",
        "",
        "The question the guardrails stand or fall on. If a flagged draft is",
        "approved as often as a clean one, the flag is decoration.",
        "",
        "| Rule | Seen | Approved | Skipped | Skip rate |",
        "|---|---:|---:|---:|---:|",
    ]
    rows = sorted(
        result["by_flag"].items(),
        key=lambda kv: -(kv[1]["approved"] + kv[1]["skipped"]),
    )
    for code, counts in rows:
        seen = counts["approved"] + counts["skipped"]
        lines.append(
            f"| {code} {counts['label']} | {seen} | {counts['approved']} | "
            f"{counts['skipped']} | {_pct(counts['skipped'], seen)} |"
        )
    clean = result["clean"]
    clean_seen = clean["approved"] + clean["skipped"]
    lines.append(
        f"| _no flags at all_ | {clean_seen} | {clean['approved']} | "
        f"{clean['skipped']} | {_pct(clean['skipped'], clean_seen)} |"
    )
    lines += [
        "",
        f"**Read this line first:** clean drafts were skipped {_pct(clean['skipped'], clean_seen)} "
        "of the time. Any rule whose skip rate is not clearly above that is not "
        "earning its place on the screen.",
        "",
        "## What they refused, in their words",
        "",
    ]
    if result["reasons"]:
        for reason, count in result["reasons"].most_common(25):
            lines.append(f"- {'**×' + str(count) + '** ' if count > 1 else ''}{reason}")
    else:
        lines.append("- Nothing was skipped, or no reasons were recorded.")

    lines += ["", "## What the system did to them", ""]
    lines.append(f"- **{len(result['blocked'])}** drafts the gate refused outright")
    for item in result["blocked"][:10]:
        lines.append(f"  - {item.get('full_name') or 'unknown'}: {(item.get('draft_text') or '')[:90]}…")

    lines += [
        "",
        "## Caveats worth stating out loud",
        "",
        "- Time per decision is the gap between consecutive ledger entries, so it",
        f"  counts reading time and hesitation but drops any gap over {BREAK_SECONDS}s as a break.",
        "- Flags are recomputed from the text as it stands now. A draft edited",
        "  before approval is scored on the edited version, which is the honest",
        "  reading of 'what did the reviewer act on'.",
        "- One reviewer, one day. This says whether the tool is usable; it does",
        "  not say the rules are right.",
    ]
    return "\n".join(lines) + "\n"


def _pct(part: int, whole: int) -> str:
    return f"{(100 * part / whole):.0f}%" if whole else "—"


def _p90(values: list) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to the SQLite database")
    parser.add_argument("--since", help="YYYY-MM-DD, inclusive")
    parser.add_argument("--until", help="YYYY-MM-DD, exclusive")
    parser.add_argument("--out", default="SESSION_REPORT.md")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"no database at {args.db}")
        return 1

    data = load(args.db, _parse_day(args.since), _parse_day(args.until))
    if not data["activity"]:
        print("No approve/reject activity in that range — nothing to report.")
        return 1

    result = analyse(data)
    report = render(result, args.db)
    Path(args.out).write_text(report, encoding="utf-8")
    print(report)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
