import asyncio
import sys
import sqlalchemy.ext.asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

passwords = ["postgres", "", "admin", "root", "1234", "123456", "password", "Mohommed", "Adil"]

async def test_password(password):
    url = f"postgresql+psycopg://postgres:{password}@localhost:5432/postgres" if password else "postgresql+psycopg://postgres@localhost:5432/postgres"
    engine = sqlalchemy.ext.asyncio.create_async_engine(url)
    try:
        async with engine.connect() as conn:
            print(f"SUCCESS: Connected with password='{password}'")
            return password
    except Exception as e:
        err_msg = str(e)
        if "password authentication failed" in err_msg:
            print(f"FAILED: password='{password}' (Auth failed)")
        else:
            print(f"FAILED: password='{password}' (Other error: {err_msg[:100]})")
        return None
    finally:
        await engine.dispose()

async def main():
    for pw in passwords:
        res = await test_password(pw)
        if res is not None:
            break

if __name__ == "__main__":
    asyncio.run(main())
