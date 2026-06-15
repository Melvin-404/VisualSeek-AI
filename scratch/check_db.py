import asyncio
from sqlalchemy import create_engine, text

async def main():
    # Try port 5432 first, then 5435
    urls = [
        "postgresql+psycopg://postgres:postgres@localhost:5435/postgres",
        "postgresql+psycopg://postgres:root@localhost:5435/postgres",
        "postgresql+psycopg://postgres:root@localhost:5432/postgres",
        "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    ]
    for url in urls:
        try:
            print(f"Trying to connect to: {url}")
            # Use synchronous connection style for easy query checks
            sync_url = url.replace("postgresql+psycopg://", "postgresql://")
            engine = create_engine(sync_url)
            with engine.connect() as conn:
                res = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).all()
                print("Tables:")
                for row in res:
                    print(f" - {row[0]}")
                
                # Check detected_objects count
                count = conn.execute(text("SELECT count(*) FROM detected_objects")).scalar()
                print(f"detected_objects count: {count}")
                
                # Check video_segments count
                count_seg = conn.execute(text("SELECT count(*) FROM video_segments")).scalar()
                print(f"video_segments count: {count_seg}")
                
                # Check cameras count
                count_cam = conn.execute(text("SELECT count(*) FROM cameras")).scalar()
                print(f"cameras count: {count_cam}")
                
                # Sample cameras
                cams = conn.execute(text("SELECT id, name, location FROM cameras")).all()
                for c in cams:
                    print(f"  Camera: id={c[0]} name='{c[1]}' location='{c[2]}'")
                
                print("Connection SUCCESS!")
                break
        except Exception as e:
            print(f"Failed to connect to {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
