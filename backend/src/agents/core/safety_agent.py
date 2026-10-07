"""
Safety agent.

Owns compliance and bot-detection avoidance: verifies the global
``AccountRateLimiter`` is the sole cap authority, trips accounts into a
``rate_limited`` / backoff state on 429s or verification challenges, and
exposes an org/account kill-switch.

Phase 0 ships a booting skeleton; the guardrail logic is implemented in the
safety phase.
"""

from src.agents.core._skeleton import SkeletonAgent


class SafetyAgent(SkeletonAgent):
    CAPABILITIES = [
        "rate_limit_guard",
        "anomaly_backoff",
        "challenge_detection",
        "kill_switch",
    ]
