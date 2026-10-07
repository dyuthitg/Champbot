"""
Declarative base and model registry.

All SQLAlchemy models across the project inherit from the single ``Base``
defined here so that ``Base.metadata`` sees every table (needed for Alembic
autogeneration and for ``create_all`` in tests).

When you add a new models module, register it in ``import_all_models`` so its
tables are attached to the shared metadata even if nothing has imported the
module yet.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the project."""
    pass


def import_all_models() -> None:
    """
    Import every models module so ``Base.metadata`` is fully populated.

    Import lazily (inside the function) to avoid circular imports at module
    load time. Call this before ``Base.metadata.create_all`` or Alembic
    autogeneration.
    """
    # Campaign management (existing)
    from src.campaigns import models as _campaigns  # noqa: F401

    # Multi-tenant models
    from src.tenancy import models as _tenancy  # noqa: F401
    from src.accounts import models as _accounts  # noqa: F401

    # Targeting + outreach (ICP, prospects, suggestions)
    from src.targeting import models as _targeting  # noqa: F401
    from src.outreach import models as _outreach  # noqa: F401

    # Warm-up activity ledger (graduation, funnel, outcome attribution)
    from src.warmup import models as _warmup  # noqa: F401

    # Registered as they are added:
    # from src.ingestion import models as _ingestion  # noqa: F401
    # from src.content import models as _content  # noqa: F401
    # from src.sequences import models as _sequences  # noqa: F401
    # from src.inbox import models as _inbox  # noqa: F401
    # from src.settings import models as _settings  # noqa: F401
