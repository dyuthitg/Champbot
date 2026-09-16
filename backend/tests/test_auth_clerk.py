"""
Clerk auth + tenancy tests.

Generates a throwaway RSA keypair, publishes it as a JWKS, signs Clerk-style
tokens, and drives GET /api/v1/me end-to-end against in-memory SQLite. Proves:
signature verification, JIT provisioning of Org+User, idempotent resolution,
and rejection of missing/invalid/expired tokens -- all without real Clerk keys.
"""

import json
import time

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.api.middleware.clerk import ClerkConfig, ClerkVerifier, set_verifier
from src.database.models import Base, import_all_models
from src.database.session import get_db

pytestmark = pytest.mark.asyncio

KID = "test-key-1"


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    jwks = {"keys": [jwk]}
    return private_key, jwks


def make_token(private_key, *, sub="user_abc", email="a@b.com", org_id=None, exp_delta=3600):
    claims = {"sub": sub, "email": email, "exp": int(time.time()) + exp_delta}
    if org_id:
        claims["org_id"] = org_id
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


@pytest_asyncio.fixture
async def client(keypair):
    private_key, jwks = keypair

    # In-memory SQLite shared across sessions via StaticPool.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import_all_models()
    async with engine.begin() as conn:
        # Only the cross-dialect tenancy/account tables (campaigns use JSONB).
        from src.tenancy.models import Organization, User
        from src.accounts.models import ConnectedAccount
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                Organization.__table__,
                User.__table__,
                ConnectedAccount.__table__,
            ],
        )

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    set_verifier(ClerkVerifier(ClerkConfig(), jwks=jwks))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    set_verifier(None)
    await engine.dispose()


async def test_me_requires_auth(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_me_rejects_garbage_token(client):
    resp = await client.get("/api/v1/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


async def test_me_provisions_user_and_org(client, keypair):
    private_key, _ = keypair
    token = make_token(private_key, sub="user_1", email="one@example.com")
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["clerk_user_id"] == "user_1"
    assert data["email"] == "one@example.com"
    assert data["user_id"] and data["org_id"]
    # Personal workspace -> user is owner.
    assert data["role"] == "owner"


async def test_me_is_idempotent(client, keypair):
    private_key, _ = keypair
    token = make_token(private_key, sub="user_2")
    r1 = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    r2 = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["user_id"] == r2.json()["user_id"]
    assert r1.json()["org_id"] == r2.json()["org_id"]


async def test_me_rejects_expired_token(client, keypair):
    private_key, _ = keypair
    token = make_token(private_key, sub="user_3", exp_delta=-10)
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_clerk_org_token_groups_users(client, keypair):
    """Two users sharing a Clerk org resolve to the same local org."""
    private_key, _ = keypair
    t1 = make_token(private_key, sub="user_4", org_id="org_shared")
    t2 = make_token(private_key, sub="user_5", org_id="org_shared")
    r1 = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {t1}"})
    r2 = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {t2}"})
    assert r1.json()["org_id"] == r2.json()["org_id"]
    assert r1.json()["user_id"] != r2.json()["user_id"]
