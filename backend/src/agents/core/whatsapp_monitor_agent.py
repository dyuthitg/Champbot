"""
WhatsApp monitor agent.

Hosts the pluggable link-ingestion sources (OpenWA admin group-listener and the
Meta WhatsApp Business Cloud API webhook), normalizes shared links into a single
``SharedLinkEvent`` stream, and fans each out to per-account relevance
evaluation so each connected bot only acts on links relevant to its ICP.

Phase 0 ships a booting skeleton; the ingestion sources and fan-out are
implemented in the WhatsApp ingestion phase.
"""

from src.agents.core._skeleton import SkeletonAgent


class WhatsAppMonitorAgent(SkeletonAgent):
    CAPABILITIES = [
        "openwa_group_listener",
        "whatsapp_cloud_webhook",
        "link_normalization",
        "relevance_fanout",
    ]
