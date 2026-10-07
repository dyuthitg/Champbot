"""
Analytics agent.

Rolls up ``events:*`` (interactions, replies, acceptances) into per-account and
per-org metrics (acceptance %, reply rate, throughput) that feed the dashboard's
agent monitor and status panels.

Phase 0 ships a booting skeleton; the metric rollups are implemented in the
analytics phase.
"""

from src.agents.core._skeleton import SkeletonAgent


class AnalyticsAgent(SkeletonAgent):
    CAPABILITIES = [
        "event_rollup",
        "throughput_metrics",
        "acceptance_reply_rates",
    ]
