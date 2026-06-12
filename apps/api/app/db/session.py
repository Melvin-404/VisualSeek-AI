from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# Create the async engine.
# SQLAlchemy uses psycopg3 dynamically via the postgresql+psycopg dialect.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

# Async session maker
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injecting an async SQLAlchemy session.
    
    Yields:
        AsyncSession: The active transactional session.
    """
    async with async_session_maker() as session:
        try:
            # Set the RLS context variable if tenant_id is set in the request context
            from app.core.exceptions import tenant_id_ctx
            from sqlalchemy import text
            tenant_id = tenant_id_ctx.get()
            if tenant_id:
                await session.execute(
                    text("SELECT set_config('app.current_org_id', :org_id, true)"),
                    {"org_id": tenant_id}
                )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
