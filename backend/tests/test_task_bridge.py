"""
Tests for the campaign<->agent Redis bridge (MessageOrchestrator).

Uses fakeredis pub/sub to assert that submitting a task publishes one
interaction command per account, stores the task->campaign mapping, and that
result events parse back into task updates.
"""

import asyncio
import json

import pytest
import fakeredis.aioredis

from src.infrastructure.task_bridge import (
    MessageOrchestrator,
    INTERACTION_CHANNEL,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def redis_client():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def _collect(pubsub, n, timeout=2.0):
    """Collect n published messages from a subscribed pubsub."""
    out = []
    async def reader():
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                out.append(json.loads(msg["data"]))
                if len(out) >= n:
                    break
    await asyncio.wait_for(reader(), timeout=timeout)
    return out


async def test_submit_publishes_one_command_per_account(redis_client):
    bridge = MessageOrchestrator(redis_client)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(INTERACTION_CHANNEL)

    reader = asyncio.create_task(_collect(pubsub, 2))
    await asyncio.sleep(0.05)  # ensure subscription is active

    task_id = await bridge.submit_linkedin_automation_task(
        url="https://linkedin.com/posts/abc",
        account_ids=["acct-1", "acct-2"],
        like=True,
        comment=True,
        priority=2,
        source="campaign:xyz",
    )

    messages = await reader
    assert len(messages) == 2
    assert {m["account_id"] for m in messages} == {"acct-1", "acct-2"}
    for m in messages:
        assert m["type"] == "queue_interaction"
        assert m["task_id"] == task_id
        assert m["url"] == "https://linkedin.com/posts/abc"
        assert m["actions"] == {"like": True, "comment": True}
        assert m["priority"] == 2


async def test_submit_stores_task_metadata(redis_client):
    bridge = MessageOrchestrator(redis_client)
    task_id = await bridge.submit_linkedin_automation_task(
        url="https://linkedin.com/in/someone",
        account_ids=["acct-1"],
    )
    meta = await bridge.get_task(task_id)
    assert meta is not None
    assert meta["url"] == "https://linkedin.com/in/someone"
    assert meta["accounts"] == ["acct-1"]
    assert meta["status"] == "submitted"


async def test_parse_result_event_completed():
    r = MessageOrchestrator.parse_result_event(
        json.dumps({"task_id": "t1", "status": "completed", "result": {"liked": True}})
    )
    assert r is not None
    assert r.task_id == "t1"
    assert r.status == "completed"
    assert r.result == {"liked": True}


async def test_parse_result_event_infers_failed_on_error():
    r = MessageOrchestrator.parse_result_event(json.dumps({"task_id": "t2", "error": "boom"}))
    assert r.status == "failed"


async def test_parse_result_event_rejects_malformed():
    assert MessageOrchestrator.parse_result_event("not json") is None
    assert MessageOrchestrator.parse_result_event(json.dumps({"no": "task_id"})) is None
