"""
WebSocket fan-out tests.

Guards the regression that motivated the realtime module: a WebSocket
connection to ``/ws/updates`` was rejected with 403 because no route existed.
These tests assert the endpoints are registered and that the connection manager
accepts sockets and fans messages out to the right clients.
"""

import pytest

pytestmark = pytest.mark.asyncio


class FakeWebSocket:
    """Duck-typed stand-in for a Starlette WebSocket."""

    def __init__(self):
        self.accepted = False
        self.sent = []
        self.disconnected = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.sent.append(message)

    async def close(self, code=1000):
        self.disconnected = True


def test_websocket_routes_are_registered(api_client):
    """The /ws/updates and /ws/campaigns/{id} endpoints must exist on the app."""
    from src.api.main import app

    paths = {r.path for r in app.routes}
    assert "/ws/updates" in paths
    assert "/ws/campaigns/{campaign_id}" in paths


async def test_connection_manager_broadcasts_to_general():
    from src.api.realtime import ConnectionManager, build_message

    manager = ConnectionManager()
    ws = FakeWebSocket()
    await manager.connect(ws)
    assert ws.accepted

    msg = build_message("CAMPAIGN_UPDATE", data={"status": "running"})
    await manager.broadcast(msg)

    assert len(ws.sent) == 1
    assert ws.sent[0]["type"] == "CAMPAIGN_UPDATE"
    assert ws.sent[0]["data"] == {"status": "running"}


async def test_connection_manager_campaign_scoped():
    from src.api.realtime import ConnectionManager, build_message

    manager = ConnectionManager()
    general = FakeWebSocket()
    campaign = FakeWebSocket()
    other = FakeWebSocket()
    await manager.connect(general)
    await manager.connect_campaign(campaign, "abc")
    await manager.connect_campaign(other, "xyz")

    msg = build_message("CAMPAIGN_UPDATE", campaign_id="abc", data={"status": "paused"})
    await manager.broadcast_to_campaign("abc", msg)

    # Only the subscribed campaign socket gets the scoped message.
    assert len(campaign.sent) == 1
    assert campaign.sent[0]["campaign_id"] == "abc"
    assert other.sent == []
    assert general.sent == []


async def test_connection_manager_disconnect_removes_socket():
    from src.api.realtime import ConnectionManager

    manager = ConnectionManager()
    ws = FakeWebSocket()
    await manager.connect_campaign(ws, "abc")
    assert manager.count == 1

    manager.disconnect(ws)
    assert manager.count == 0
