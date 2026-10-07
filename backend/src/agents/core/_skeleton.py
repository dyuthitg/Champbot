"""
Skeleton agent base.

Several agents are declared in the default configuration (``safety``,
``scheduler``, ``whatsapp_monitor``, ``analytics``) but their full behavior is
built out across later phases. Until then they need to *exist* as real
``BaseAgent`` subclasses so the orchestrator can import and boot the configured
topology instead of crashing with ``ModuleNotFoundError``.

``SkeletonAgent`` is a minimal but real agent: it initializes, participates in
the heartbeat/health loops provided by ``BaseAgent``, advertises its intended
capabilities, and runs no background work. Each concrete phase replaces the
relevant subclass's ``_start_agent_tasks``/handlers with real logic.
"""

import asyncio
from typing import List

from src.agents.base_agent import BaseAgent


class SkeletonAgent(BaseAgent):
    """A real, no-op placeholder agent that boots cleanly."""

    #: Capabilities this agent will advertise once implemented.
    CAPABILITIES: List[str] = []

    async def _initialize_agent(self) -> None:
        self.logger.info(
            "Skeleton agent initialized (placeholder; full behavior lands in a later phase)",
            capabilities=self.CAPABILITIES,
        )

    async def _start_agent_tasks(self) -> List[asyncio.Task]:
        # No background loops yet.
        return []

    def _get_capabilities(self) -> List[str]:
        return list(self.CAPABILITIES)

    async def _on_start(self) -> None:
        pass

    async def _on_stop(self) -> None:
        pass
