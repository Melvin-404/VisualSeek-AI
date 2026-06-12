import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uuid
from sqlalchemy import text
from app.db.session import async_session_maker

async def main():
    async with async_session_maker() as session:
        async with session.begin():
            print("Disabling triggers...")
            await session.execute(text("ALTER TABLE audit_log DISABLE TRIGGER ALL"))
            await session.execute(text("ALTER TABLE organizations DISABLE TRIGGER ALL"))
            print("Triggers disabled successfully!")
            
            print("Enabling triggers...")
            await session.execute(text("ALTER TABLE audit_log ENABLE TRIGGER ALL"))
            await session.execute(text("ALTER TABLE organizations ENABLE TRIGGER ALL"))
            print("Triggers enabled successfully!")

if __name__ == "__main__":
    asyncio.run(main())
