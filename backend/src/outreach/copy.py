"""
Humanistic copywriting for outreach.

Writes the connection notes, first messages and comments that go out *as the
user*. Two hard requirements shape this module:

1. **It has to sound like a person.** Not "personalized" in the mail-merge
   sense — actually specific. The prompt is built from what we genuinely know
   about the recipient, and the model is told to say nothing it cannot ground
   in that. Copy that could have been sent to anyone is a failure, and the
   quality gate treats it as one.

2. **It has to survive without a model.** If no OpenRouter key is configured,
   generation falls back to templates that are deliberately plain and still
   clear the quality gate. A missing API key degrades the writing; it never
   produces something embarrassing and never blocks the product.

Generated copy is re-drafted (up to ``MAX_ATTEMPTS``) when the quality gate
rejects it, with the specific failures fed back into the retry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

from src.infrastructure.llm.provider import LLMProvider, OpenRouterConfig, Slot
from src.outreach import brand_voice as brand_voice_module
from src.outreach.quality import QualityReport, check_copy

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

# The rules that make outreach read as human. Written as prohibitions because
# models comply with concrete "never do X" far better than with "be authentic".
_STYLE_RULES = """\
Voice and rules — follow all of them:
- Write like one professional messaging another, not like marketing copy.
- Before you write anything, find the ONE most distinctive, unusual detail in
  what you were given — a specific number, an admission, an unusual choice,
  a concrete consequence. Not their industry, not their job title, not the
  general topic of their post — the one detail that would NOT also be true
  of five other people's similar update. Build the whole comment around that
  detail. There is almost always one in the text you were given; look again
  before settling for their industry or job title as the "specific" detail.
- Never invent facts, mutual connections, shared events, or prior conversations.
- No flattery ("impressive background", "love what you're doing").
- Banned phrases: "I hope this finds you well", "quick question", "just
  reaching out", "I came across your profile", "pick your brain", "synergy",
  "game-changer", "touch base", "circle back".
- No links, no calendar links, no asking for a meeting or a call.
- No emoji. At most one exclamation mark, and preferably none.
- Contractions are good. Short sentences are good. Hedging is not.
- Do not use their full name; use their first name only, or no name at all.
- Output ONLY the message text. No subject line, no signature, no quotes,
  no preamble, no explanation."""


@dataclass
class DraftResult:
    """A drafted message plus how it was produced and how good it is."""

    text: str
    generated_by: str            # "openrouter:<model>" | "template"
    quality: QualityReport
    attempts: int = 1
    rationale: str = ""


def _first_name(target: Any) -> str:
    name = _get(target, "first_name")
    if not name:
        full = _get(target, "full_name") or ""
        name = str(full).split()[0] if full else ""
    return str(name or "").strip()


def _get(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _profile_brief(target: Any) -> str:
    """Everything we actually know about the recipient, as prompt context."""
    lines = []
    for label, field in (
        ("Name", "full_name"),
        ("Title", "title"),
        ("Company", "company"),
        ("Headline", "headline"),
        ("Industry", "industry"),
        ("Location", "location"),
    ):
        value = _get(target, field)
        if value:
            lines.append(f"- {label}: {value}")

    context = _get(target, "context") or {}
    if isinstance(context, dict):
        if context.get("post_text"):
            lines.append(f"- Recent post by them: \"{str(context['post_text'])[:400]}\"")
        if context.get("how_found"):
            lines.append(f"- How we found them: {context['how_found']}")
        if context.get("shared_group"):
            lines.append(f"- Shared group: {context['shared_group']}")
    return "\n".join(lines) or "- (no profile details available)"


def _sender_brief(account: Any, icp: Any) -> str:
    lines = []
    if _get(account, "display_name"):
        lines.append(f"- Name: {_get(account, 'display_name')}")
    if _get(account, "headline"):
        lines.append(f"- Headline: {_get(account, 'headline')}")
    if _get(icp, "value_proposition"):
        lines.append(f"- What they help with: {_get(icp, 'value_proposition')}")
    return "\n".join(lines) or "- (sender profile not set)"


def _task_for(action: str, target: Any) -> str:
    first = _first_name(target)
    who = f"{first}" if first else "this person"
    if action == "connect":
        return (
            f"Write a LinkedIn connection request note to {who}. "
            f"Under 280 characters, hard limit 300. "
            f"Its only job is to make connecting feel worthwhile — say why them, "
            f"specifically. Do not pitch, do not sell, do not ask for anything."
        )
    if action == "message":
        return (
            f"Write a first LinkedIn message to {who}, who has just accepted a "
            f"connection request. Two or three short sentences, under 500 "
            f"characters. Open a conversation about something relevant to them. "
            f"You may say what you do in one clause, but do not pitch and do not "
            f"ask for a meeting. End with a genuine, low-effort question."
        )
    if action == "comment":
        return (
            f"Write a LinkedIn comment on {who}'s post. One or two sentences, "
            f"under 300 characters. Add a specific thought, an example, or a real "
            f"question about what they said. Never 'Great post!'. Never mention "
            f"your own product."
        )
    raise ValueError(f"no copy task defined for action: {action}")


def build_messages(action: str, target: Any, account: Any, icp: Any) -> List[dict]:
    """Assemble the chat messages for one drafting call."""
    instructions = _get(icp, "instructions")
    system = (
        "You write LinkedIn outreach on behalf of a real professional. Your copy "
        "is sent under their name, so it must sound like them and never like a "
        "sales tool.\n\n" + _STYLE_RULES
    )
    if instructions:
        system += (
            "\n\nAdditional standing instructions from the account owner — these "
            f"override the defaults above where they conflict:\n{instructions}"
        )

    brand_voice = brand_voice_module.load_profile(_get(icp, "brand_voice_id"))
    if brand_voice:
        system += (
            "\n\nBrand voice for this account — layer this tone on top of "
            "everything above. It shapes *how* this is said; it never "
            "overrides the safety rules (no invented facts, no links, no "
            "pitching):\n" + brand_voice_module.render_style_rules(brand_voice)
        )

    user = (
        f"Sender (you are writing as them):\n{_sender_brief(account, icp)}\n\n"
        f"Recipient:\n{_profile_brief(target)}\n\n"
        f"Task: {_task_for(action, target)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def draft(
    action: str,
    target: Any,
    account: Any,
    icp: Any,
    *,
    provider: Optional[LLMProvider] = None,
    org_id: Optional[str] = None,
) -> DraftResult:
    """
    Draft copy for one action, retrying against the quality gate.

    Falls back to a template when no provider is configured or every attempt is
    rejected — the caller always gets something reviewable, and the quality
    report travels with it so the UI can show exactly what is weak.
    """
    provider = provider or _default_provider()

    if provider is not None:
        messages = build_messages(action, target, account, icp)
        best: Optional[DraftResult] = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = await provider.complete(
                    Slot.CONTENT, messages, org_id=org_id, max_tokens=400
                )
            except Exception as exc:
                logger.warning("Copy generation failed (attempt %s): %s", attempt, exc)
                break

            text = _clean(result.text)
            report = check_copy(text, action, target)
            candidate = DraftResult(
                text=text,
                generated_by=f"openrouter:{result.model}",
                quality=report,
                attempts=attempt,
                rationale=_rationale(target, icp),
            )
            if report.passed:
                return candidate
            if best is None or report.score > best.quality.score:
                best = candidate

            # Feed the specific failures back in rather than just retrying.
            issues = "; ".join(report.all_issues) or "it read as generic outreach"
            messages = messages + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        f"That draft was rejected: {issues}. "
                        f"Rewrite it fixing every one of those problems. "
                        f"Output only the corrected message."
                    ),
                },
            ]

        if best is not None and best.quality.score >= 55:
            # Below the pass bar but worth a human's judgement; the UI shows why.
            return best

    return _template_draft(action, target, account, icp)


def _default_provider() -> Optional[LLMProvider]:
    """Build a provider from env, or None when OpenRouter isn't configured."""
    config = OpenRouterConfig.from_env()
    if not config.api_key:
        return None
    return LLMProvider(config)


def _clean(text: str) -> str:
    """Strip the wrappers models add despite being told not to."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.strip("`")
        if "\n" in body:
            body = body.split("\n", 1)[1]
    body = body.strip()
    # Unwrap a fully-quoted message.
    if len(body) > 1 and body[0] in "\"'" and body[-1] == body[0]:
        body = body[1:-1].strip()
    for prefix in ("Message:", "Note:", "Comment:", "Here's", "Here is"):
        if body.lower().startswith(prefix.lower()):
            _, _, rest = body.partition(":")
            if rest.strip():
                body = rest.strip()
            break
    return body.strip()


def _rationale(target: Any, icp: Any) -> str:
    """One line explaining to the reviewer why this person, in plain English."""
    reasons = _get(target, "relevance_reasons") or []
    score = _get(target, "relevance_score") or 0
    icp_name = _get(icp, "name") or "your ICP"
    if reasons:
        return f"{score}% match to {icp_name} — " + "; ".join(list(reasons)[:3])
    return f"{score}% match to {icp_name}"


# ----------------------------------------------------------------------
# Template fallback
# ----------------------------------------------------------------------


def _template_draft(action: str, target: Any, account: Any, icp: Any) -> DraftResult:
    """
    Plain, honest copy that works without a model.

    These are written to be unremarkable rather than clever: they state a real
    reason for the contact using details we actually hold, and stop. They clear
    the quality gate, which is the bar that matters.
    """
    first = _first_name(target) or "there"
    company = _get(target, "company")
    title = _get(target, "title")
    industry = _get(target, "industry")
    context = _get(target, "context") or {}
    post_text = context.get("post_text") if isinstance(context, dict) else None

    # Pick the most specific true detail we have about them. Phrasing matters:
    # "your work leading head of growth at Northwind" is the kind of mangled
    # slot-filling that gives templated outreach away.
    if company and title:
        detail = f"your work as {title} at {company}"
    elif company:
        detail = f"your work at {company}"
    elif title:
        detail = f"your work as {title}"
    elif industry:
        detail = f"your work in {industry.lower()}"
    else:
        detail = "the work you're doing"

    if action == "connect":
        text = (
            f"Hi {first} — I follow what's happening in this space and {detail} "
            f"stood out. Would be glad to connect and keep an eye on what you share."
        )
    elif action == "message":
        opener = (
            f"Thanks for connecting, {first}."
            if first != "there"
            else "Thanks for connecting."
        )
        question = (
            "What's proving hardest about that at the moment?"
            if company
            else "What are you focused on this quarter?"
        )
        text = f"{opener} I've been paying attention to {detail}. {question}"
    elif action == "comment":
        if post_text:
            text = (
                f"This matches what I keep seeing, {first} — the hard part is "
                f"usually getting everyone to agree on it first. How did you "
                f"handle that?"
            )
        else:
            text = (
                f"Useful point, {first} — the part about {detail} is the bit most "
                f"people skip. What changed your thinking on it?"
            )
    else:
        raise ValueError(f"no template for action: {action}")

    text = text.strip()
    return DraftResult(
        text=text,
        generated_by="template",
        quality=check_copy(text, action, target),
        rationale=_rationale(target, icp),
    )
