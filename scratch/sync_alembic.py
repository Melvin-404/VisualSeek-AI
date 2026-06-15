import psycopg

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5435/postgres")
with conn.cursor() as cur:
    cur.execute("UPDATE alembic_version SET version_num = '44d6cb9353df'")
conn.commit()
conn.close()
print("Alembic version synchronized to 44d6cb9353df")
