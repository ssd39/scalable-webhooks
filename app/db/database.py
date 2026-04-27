from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# ---------------------------------------------------------------------------
# Async engine + session – used by FastAPI routes (API layer)
# ---------------------------------------------------------------------------

async_engine = create_async_engine(
    settings.database_url,
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# Sync engine + session – used by RQ worker tasks (sync context)
# ---------------------------------------------------------------------------

sync_engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative Base shared by all ORM models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    All models must inherit from this class so that Alembic's autogenerate
    can detect schema changes automatically.
    """
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency – async session
# ---------------------------------------------------------------------------


async def get_db() -> AsyncSession:
    """Yield an async DB session; commits on success, rolls back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Worker helper – sync context manager
# ---------------------------------------------------------------------------


def get_sync_db() -> Session:
    """Return a sync DB session for use in RQ worker tasks."""
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


async def dispose_engine() -> None:
    """Dispose async engine connection pool on application shutdown."""
    await async_engine.dispose()
