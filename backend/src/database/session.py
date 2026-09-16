from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
import os
from contextlib import asynccontextmanager

# Database configuration
# Priority: DATABASE_URL (Railway/generic) > SUPABASE_DB_URL > SQLite (testing)
#           > individual Local/Docker PostgreSQL components.
DATABASE_URL_ENV = os.getenv("DATABASE_URL")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
USE_SQLITE = os.getenv("USE_SQLITE", "false").lower() == "true"


def _to_asyncpg(url: str) -> str:
    """Normalize a Postgres URL to the asyncpg driver."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


connect_args = {}
pool_class = NullPool

if USE_SQLITE:
    # SQLite for local testing when no PostgreSQL available
    DATABASE_URL = "sqlite+aiosqlite:///./test_campaigns.db"
    connect_args = {"check_same_thread": False}
    pool_class = StaticPool
elif DATABASE_URL_ENV:
    # Railway (and most PaaS) provide a single DATABASE_URL.
    DATABASE_URL = _to_asyncpg(DATABASE_URL_ENV)
    if "pooler.supabase.com" in DATABASE_URL_ENV:
        connect_args = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
elif SUPABASE_DB_URL:
    DATABASE_URL = _to_asyncpg(SUPABASE_DB_URL)
    # Supabase pooler requires disabling prepared statement caching for asyncpg
    # See: https://supabase.com/docs/guides/database/connecting-to-postgres
    if "pooler.supabase.com" in SUPABASE_DB_URL:
        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }
else:
    # Fallback to individual components (Local/Docker PostgreSQL)
    DB_USER = os.getenv("POSTGRES_USER", "postgres")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB", "linkedin_automation")
    DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    poolclass=pool_class,
    pool_pre_ping=True if not USE_SQLITE else False,
    connect_args=connect_args,
)

# Call factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for background tasks/scripts"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
