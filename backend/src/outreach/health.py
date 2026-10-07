"""
Account health: the acceptance-rate governor.

Most automation tooling governs on volume, because volume is easy to count.
That is the wrong variable. LinkedIn restricts accounts primarily on **negative
recipient feedback** — invitations ignored, or worse, marked "I don't know this
person". An account sending 15 invitations a day at 8% acceptance is in far more
danger than one sending 25 a day at 45%, and a substantial share of restricted
accounts never exceeded the published limits at all.

So this module computes what the audience is actually doing and converts it into
a **throttle** that scales the caps down, plus a **verdict** the UI can show:

    acceptance >= 30%   healthy    full tier volume
    15% - 30%           caution    volume reduced, worth reviewing targeting
    < 15%               danger     invitations stop entirely

The throttle only ever reduces. Nothing here can raise an account above the
ceiling its warm-up stage and tier already allow.

A low acceptance rate is a *targeting or copy* problem, not a volume problem,
which is why the verdicts carry an explanation aimed at fixing the cause rather
than just reporting a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.outreach.models import OutreachSuggestion, SuggestionAction, SuggestionStatus
from src.targeting.models import OutreachTarget, TargetStatus
from src.warmup.program import ACCEPTANCE_CAUTION, ACCEPTANCE_DANGER

# Below this many invitations, an acceptance rate is noise. Two rejections out
# of three is not a 33% acceptance rate, it's a small sample.
MIN_SAMPLE = 15

HEALTHY = "healthy"
CAUTION = "caution"
DANGER = "danger"
UNKNOWN = "unknown"


@dataclass
class Funnel:
    """The outreach funnel, measured rather than projected."""

    invites_sent: int = 0
    invites_accepted: int = 0
    messages_sent: int = 0
    replies: int = 0
    interested: int = 0
    booked: int = 0

    @property
    def acceptance_rate(self) -> Optional[float]:
        if not self.invites_sent:
            return None
        return self.invites_accepted / self.invites_sent

    @property
    def reply_rate(self) -> Optional[float]:
        if not self.messages_sent:
            return None
        return self.replies / self.messages_sent

    @property
    def booking_rate(self) -> Optional[float]:
        if not self.invites_sent:
            return None
        return self.booked / self.invites_sent

    def as_dict(self) -> dict:
        return {
            "invites_sent": self.invites_sent,
            "invites_accepted": self.invites_accepted,
            "messages_sent": self.messages_sent,
            "replies": self.replies,
            "interested": self.interested,
            "booked": self.booked,
            "acceptance_rate": _pct(self.acceptance_rate),
            "reply_rate": _pct(self.reply_rate),
            "booking_rate": _pct(self.booking_rate),
        }


@dataclass
class HealthReport:
    """What the numbers say, and what to do about it."""

    verdict: str = UNKNOWN
    throttle: float = 1.0
    # Actions the account may not perform right now regardless of stage/caps.
    suspended_actions: frozenset = frozenset()
    funnel: Funnel = field(default_factory=Funnel)
    headline: str = ""
    advice: list = field(default_factory=list)
    had_challenge: bool = False

    def blocks(self, action: str) -> bool:
        return action in self.suspended_actions

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "throttle": round(self.throttle, 2),
            "suspended_actions": sorted(self.suspended_actions),
            "headline": self.headline,
            "advice": self.advice,
            "had_challenge": self.had_challenge,
            "funnel": self.funnel.as_dict(),
        }


def _pct(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value * 100, 1)


async def measure_funnel(
    db: AsyncSession, account, *, since_days: int = 90
) -> Funnel:
    """Compute the funnel for one account from its real outcomes."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)

    sent_by_action = dict(
        (
            await db.execute(
                select(OutreachSuggestion.action, func.count())
                .where(
                    OutreachSuggestion.account_id == account.id,
                    OutreachSuggestion.status == SuggestionStatus.SENT,
                    OutreachSuggestion.sent_at >= since,
                )
                .group_by(OutreachSuggestion.action)
            )
        ).all()
    )

    target_states = dict(
        (
            await db.execute(
                select(OutreachTarget.status, func.count())
                .where(OutreachTarget.account_id == account.id)
                .group_by(OutreachTarget.status)
            )
        ).all()
    )

    def targets_in(*statuses) -> int:
        return sum(int(target_states.get(s, 0)) for s in statuses)

    # Anyone who replied, was qualified as interested, or booked must also have
    # accepted the invitation first — so later stages count toward acceptance.
    accepted = targets_in(
        TargetStatus.CONNECTED, TargetStatus.REPLIED, TargetStatus.INTERESTED,
        TargetStatus.BOOKED,
    )
    replied = targets_in(
        TargetStatus.REPLIED, TargetStatus.INTERESTED, TargetStatus.BOOKED
    )

    return Funnel(
        invites_sent=int(sent_by_action.get(SuggestionAction.CONNECT, 0)),
        invites_accepted=accepted,
        messages_sent=int(sent_by_action.get(SuggestionAction.MESSAGE, 0)),
        replies=replied,
        interested=targets_in(TargetStatus.INTERESTED, TargetStatus.BOOKED),
        booked=targets_in(TargetStatus.BOOKED),
    )


def assess(funnel: Funnel, *, had_challenge: bool = False) -> HealthReport:
    """
    Turn measured outcomes into a throttle and a verdict.

    Pure function of the funnel, so it is trivially testable and the same
    numbers always produce the same governance decision.
    """
    report = HealthReport(funnel=funnel, had_challenge=had_challenge)

    if had_challenge:
        report.verdict = DANGER
        report.throttle = 0.25
        report.suspended_actions = frozenset({SuggestionAction.CONNECT})
        report.headline = "LinkedIn challenged this account — outreach paused"
        report.advice = [
            "Sign in to LinkedIn in a browser and clear the checkpoint.",
            "Leave invitations off for at least 48 hours after clearing it.",
            "Re-verify the account here once the session works again.",
        ]
        return report

    rate = funnel.acceptance_rate

    if rate is None or funnel.invites_sent < MIN_SAMPLE:
        report.verdict = UNKNOWN
        report.throttle = 1.0
        remaining = max(0, MIN_SAMPLE - funnel.invites_sent)
        report.headline = (
            f"Not enough invitations yet to judge acceptance "
            f"({funnel.invites_sent} sent, {remaining} more for a reading)"
        )
        return report

    if rate < ACCEPTANCE_DANGER:
        report.verdict = DANGER
        report.throttle = 0.0
        report.suspended_actions = frozenset({SuggestionAction.CONNECT})
        report.headline = (
            f"Acceptance rate {rate:.0%} — invitations stopped to protect the account"
        )
        report.advice = [
            "Below ~15% acceptance, LinkedIn starts treating the account as spam. "
            "This is a targeting problem, not a volume problem.",
            "Tighten the ICP: the people being invited don't recognise why you're "
            "reaching out.",
            "Engage with a prospect's posts before inviting them — warm invitations "
            "are accepted far more often than cold ones.",
            "Existing connections can still be messaged; only new invitations stop.",
        ]
        return report

    if rate < ACCEPTANCE_CAUTION:
        report.verdict = CAUTION
        # Scale smoothly between the danger and caution lines rather than
        # dropping off a cliff.
        span = ACCEPTANCE_CAUTION - ACCEPTANCE_DANGER
        report.throttle = round(0.4 + 0.5 * ((rate - ACCEPTANCE_DANGER) / span), 2)
        report.headline = f"Acceptance rate {rate:.0%} — volume reduced while this recovers"
        report.advice = [
            "Healthy accounts sit above 30%. Below that, invitation volume is "
            "reduced automatically until it recovers.",
            "Check whether the connection note gives a specific reason for "
            "reaching out to that person.",
        ]
        return report

    report.verdict = HEALTHY
    report.throttle = 1.0
    report.headline = f"Acceptance rate {rate:.0%} — healthy"
    if funnel.reply_rate is not None and funnel.reply_rate < 0.10 and funnel.messages_sent >= 10:
        report.advice.append(
            f"Invitations are landing, but only {funnel.reply_rate:.0%} of follow-up "
            f"messages get a reply. The opener is the thing to change."
        )
    return report


async def account_health(
    db: AsyncSession, account, *, had_challenge: Optional[bool] = None
) -> HealthReport:
    """Measure and assess one account in a single call."""
    if had_challenge is None:
        from src.accounts.models import AccountStatus

        had_challenge = account.status in (
            AccountStatus.RATE_LIMITED,
            AccountStatus.SUSPENDED,
        )
    funnel = await measure_funnel(db, account)
    return assess(funnel, had_challenge=had_challenge)
