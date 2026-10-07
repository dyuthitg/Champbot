"""
Agents status route.

``GET /api/v1/agents`` powers the dashboard's agent monitor. When Redis is
connected it reflects live heartbeats/state written by the agent runtime;
otherwise it returns the configured agent topology as idle so the dashboard
renders meaningfully in a fresh environment.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter(tags=["agents"])

# The agent types the dashboard renders.
_DASHBOARD_AGENTS = [
    ("account_manager", "Account Manager"),
    ("content_analysis", "Content Analysis"),
    ("interaction", "Interaction"),
    ("conversation", "Conversation"),
    ("safety", "Safety"),
]


@router.get("/agents")
async def list_agents(request: Request) -> list:
    """Return current agent statuses for the monitor board."""
    now = datetime.now(timezone.utc).isoformat()
    redis = getattr(request.app.state, "redis", None)

    agents = []
    for agent_type, display_name in _DASHBOARD_AGENTS:
        status = "idle"
        tasks_completed = 0
        tasks_failed = 0
        last_activity = now

        if redis is not None:
            try:
                # Agents write heartbeat:{id} and a registry hash agents:{id}.
                hb = await redis.exists(f"heartbeat:{agent_type}")
                status = "processing" if hb else "idle"
                metrics = await redis.hgetall(f"agent_metrics:{agent_type}")
                if metrics:
                    tasks_completed = int(metrics.get("messages_processed", 0) or 0)
                    tasks_failed = int(metrics.get("errors", 0) or 0)
            except Exception:
                status = "idle"

        agents.append(
            {
                "id": agent_type,
                "name": display_name,
                "type": agent_type,
                "status": status,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
                "last_activity": last_activity,
            }
        )
    return agents
