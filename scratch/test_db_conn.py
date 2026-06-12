import asyncio
import sys
import sqlalchemy.ext.asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    print("Creating engine...")
    engine = sqlalchemy.ext.asyncio.create_async_engine('postgresql+psycopg://postgres:postgres@localhost:5435/postgres')
    print("Attempting to connect...")
    try:
        async with engine.connect() as conn:
            print("Connected successfully!")
    except Exception as e:
        print("Connection failed:", e)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
