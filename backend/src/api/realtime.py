"""
WebSocket fan-out for real-time updates.

The REST API drives the UI, but progress is reported by the agent runtime
(a separate process) and nothing pushes those changes to the browser. This
module is the other half of that loop: it holds every open WebSocket, accepts
connections on ``/ws/updates`` and ``/ws/campaigns/{campaign_id}``, and forwards
events to the right clients.

It is deliberately process-local. Events that originate in other processes
(reports from the agent runtime) arrive over Redis and are forwarded here by
:func:`redis_forwarder`; events that originate in this process (campaign state
changes) are broadcast directly via :func:`broadcast_ws`. The manager is a
module singleton so any handler can reach it without threading ``app.state``
through every call site.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("realtime")

# Redis ``events:*`` channels published by the agent runtime, mapped to the
# frontend's WSMessage ``type`` values.
EVENT_TO_WS = {
    "interaction_completed": "TASK_COMPLETED",
    "interaction_failed": "TASK_FAILED",
}


class ConnectionManager:
    """Tracks open WebSocket connections for the general stream and per-campaign."""

    def __init__(self) -> None:
        self._general: Set[WebSocket] = set()
        self._campaigns: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._general.add(websocket)

    async def connect_campaign(self, websocket: WebSocket, campaign_id: str) -> None:
        await websocket.accept()
        self._campaigns.setdefault(campaign_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._general.discard(websocket)
        for sockets in self._campaigns.values():
            sockets.discard(websocket)
        for cid in [c for c, s in self._campaigns.items() if not s]:
            del self._campaigns[cid]

    @property
    def count(self) -> int:
        total = len(self._general)
        for sockets in self._campaigns.values():
            total += len(sockets)
        return total

    async def _send(self, websocket: WebSocket, message: Dict[str, Any]) -> bool:
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            self.disconnect(websocket)
            return False

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Send to every general and per-campaign connection."""
        await asyncio.gather(
            *(self._send(ws, message) for ws in list(self._general)),
            *(
                self._send(ws, message)
                for sockets in self._campaigns.values()
                for ws in list(sockets)
            ),
            return_exceptions=True,
        )

    async def broadcast_to_campaign(self, campaign_id: str, message: Dict[str, Any]) -> None:
        """Send only to connections subscribed to one campaign."""
        await asyncio.gather(
            *(self._send(ws, message) for ws in list(self._campaigns.get(campaign_id, ()))),
            return_exceptions=True,
        )


manager = ConnectionManager()


def build_message(
    message_type: str,
    *,
    campaign_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    data: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build a WSMessage-shaped payload matching the frontend's ``WSMessage``."""
    msg: Dict[str, Any] = {
        "type": message_type,
        "data": data if data is not None else {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if campaign_id is not None:
        msg["campaign_id"] = campaign_id
    if task_id is not None:
        msg["task_id"] = task_id
    if agent_id is not None:
        msg["agent_id"] = agent_id
    return msg


async def broadcast_ws(message_type: str, **kwargs: Any) -> None:
    """Broadcast a message to every open WebSocket."""
    await manager.broadcast(build_message(message_type, **kwargs))


async def broadcast_campaign(message_type: str, campaign_id: str, **kwargs: Any) -> None:
    """Broadcast a message to all sockets, and specifically the campaign's own."""
    msg = build_message(message_type, campaign_id=campaign_id, **kwargs)
    await manager.broadcast(msg)
    await manager.broadcast_to_campaign(campaign_id, msg)


async def websocket_updates(websocket: WebSocket) -> None:
    """``/ws/updates`` -- org-wide stream of system events."""
    await manager.connect(websocket)
    try:
        # No inbound messages are expected; receiving keeps the connection
        # alive and lets us notice a client that went away.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


async def websocket_campaign(websocket: WebSocket, campaign_id: str) -> None:
    """``/ws/campaigns/{campaign_id}`` -- events scoped to one campaign."""
    await manager.connect_campaign(websocket, campaign_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


async def redis_forwarder(redis) -> None:
    """
    Forward agent-runtime events from Redis pub/sub to WebSocket clients.

    Runs as a long-lived task started by the app lifespan. The agent runtime
    publishes on ``events:interaction_completed`` / ``events:interaction_failed``
    (see ``src/agents/core/interaction_agent.py``); we map those to the
    frontend's ``TASK_COMPLETED`` / ``TASK_FAILED`` messages and push them to the
    general stream. The agent payload does not carry a campaign id, so these
    cannot be routed to a single campaign socket -- that is fine, the frontend
    keys its invalidation off ``campaign_id`` only when present.
    """
    pubsub = redis.pubsub()
    channels = [f"events:{event_type}" for event_type in EVENT_TO_WS]
    try:
        await pubsub.subscribe(*channels)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()
            event_type = channel.removeprefix("events:")
            ws_type = EVENT_TO_WS.get(event_type)
            if not ws_type:
                continue
            try:
                data = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            await broadcast_ws(ws_type, data=data)
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.close()
