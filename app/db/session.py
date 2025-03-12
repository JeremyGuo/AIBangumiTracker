from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.database import Base
import logging

# Configure SQLAlchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)  # Only show WARNING and above
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)  # Only show WARNING and above

DATABASE_URL = "sqlite+aiosqlite:///./aibangumi.db"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Disable echo to prevent info logs
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# 添加 async_session 实例
async_session = AsyncSessionLocal

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()