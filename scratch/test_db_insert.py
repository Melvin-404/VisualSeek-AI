import asyncio
import uuid
import sys
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.models.schema_models import Organization, Camera

# Configure logging to see SQL statements
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def test_insert():
    org_id = uuid.uuid4()
    camera_id = uuid.uuid4()
    print(f"Generated org_id: {org_id}")
    print(f"Generated camera_id: {camera_id}")
    
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        async with session.begin():
            print("--- Setting app.current_org_id ---")
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, false)"),
                {"org_id": str(org_id)}
            )
            
            print("--- Instantiating models ---")
            org = Organization(id=org_id, name="Test Org Debug")
            camera = Camera(
                id=camera_id,
                org_id=org_id,
                name="Debug Camera",
                location="Debug Location",
                rtsp_url="rtsp://localhost/stream",
                status="online"
            )
            session.add(org)
            session.add(camera)
            print("--- Added to session. Exiting begin block to commit... ---")
            
    await engine.dispose()
    print("Commit completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_insert())
