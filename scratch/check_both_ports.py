import asyncio
from sqlalchemy import create_engine, text

def check_db(url):
    print(f"\nChecking: {url}")
    try:
        engine = create_engine(url.replace("postgresql+psycopg://", "postgresql://"))
        with engine.connect() as conn:
            # Check users
            users = conn.execute(text("SELECT count(*) FROM users")).scalar()
            print(f"Users count: {users}")
            # Check cameras
            cams = conn.execute(text("SELECT count(*) FROM cameras")).scalar()
            print(f"Cameras count: {cams}")
            # Check segments
            segs = conn.execute(text("SELECT count(*) FROM video_segments")).scalar()
            print(f"Video segments count: {segs}")
            # Check detected_objects
            objs = conn.execute(text("SELECT count(*) FROM detected_objects")).scalar()
            print(f"Detected objects count: {objs}")
            if cams > 0:
                print("Cameras:")
                for r in conn.execute(text("SELECT id, name, status FROM cameras")).all():
                    print(f" - ID: {r[0]}, Name: {r[1]}, Status: {r[2]}")
    except Exception as e:
        print(f"Error checking {url}: {e}")

if __name__ == "__main__":
    check_db("postgresql+psycopg://postgres:postgres@localhost:5435/postgres")
    check_db("postgresql+psycopg://postgres:root@localhost:5435/postgres")
    check_db("postgresql+psycopg://postgres:root@localhost:5432/postgres")
    check_db("postgresql+psycopg://postgres:postgres@localhost:5432/postgres")
