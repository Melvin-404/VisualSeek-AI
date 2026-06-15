import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = AsyncSession(engine)
    
    def test_fn(sync_obj):
        print("Received object type:", type(sync_obj))
        print("Available attributes/methods:", [x for x in dir(sync_obj) if not x.startswith('_')])
        
    await async_session.run_sync(test_fn)
    await async_session.close()

if __name__ == "__main__":
    asyncio.run(main())
