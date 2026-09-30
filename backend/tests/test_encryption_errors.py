"""
Credential-encryption failures surface as clear API errors, not HTTP 500s.

A missing ENCRYPTION_KEY is a deployment misconfiguration (503), and a stored
cookie that no longer decrypts is a per-account problem the user can fix by
re-entering cookies (409). Neither is a server crash.
"""

import pytest

pytestmark = pytest.mark.asyncio

COOKIE = "AQEDATfakeLiAtCookieValue0123456789"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_connect_without_encryption_key_is_503(api_client, issue_token, monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_DEV_ENCRYPTION", raising=False)

    resp = await api_client.post(
        "/api/v1/accounts",
        json={"li_at": COOKIE},
        headers=auth(issue_token("user_alice", org="org_alpha")),
    )

    assert resp.status_code == 503
    assert "ENCRYPTION_KEY" in resp.json()["detail"]
    # The operator hint (how to generate a key) stays in the server log.
    assert "Fernet" not in resp.json()["detail"]


async def test_rotated_key_makes_verify_409_not_500(api_client, issue_token, monkeypatch):
    from src.accounts import service as accounts_service

    async def _no_network(record, creds, transport):
        return None

    # Connecting normally verifies against LinkedIn; skip that so the test is offline.
    monkeypatch.setattr(accounts_service, "_verify_and_apply", _no_network)
    monkeypatch.setenv("ENCRYPTION_KEY", "first-key-used-to-store-the-cookie")
    token = issue_token("user_alice", org="org_alpha")

    created = await api_client.post("/api/v1/accounts", json={"li_at": COOKIE}, headers=auth(token))
    assert created.status_code == 201
    account_id = created.json()["id"]

    monkeypatch.setenv("ENCRYPTION_KEY", "a-different-key-after-rotation")
    for path in ("verify", "preflight"):
        resp = await api_client.post(f"/api/v1/accounts/{account_id}/{path}", headers=auth(token))
        assert resp.status_code == 409, path
        assert "cookies" in resp.json()["detail"]
