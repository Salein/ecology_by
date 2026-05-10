import os
import psycopg

u = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
conn = psycopg.connect(u)
c = conn.cursor()
c.execute("select count(*) from registry_records")
print("records", c.fetchone()[0])
c.execute("select updated_at, sources, import_sources_detail from registry_cache_meta where id=1")
row = c.fetchone()
print("updated_at", row[0])
print("sources", row[1])
d = row[2]
if d:
    print("import_sources_detail entries", len(d) if isinstance(d, list) else d)
    for x in (d if isinstance(d, list) else [])[:5]:
        print(" ", x)
c.execute("select count(*) from registry_records where coalesce(trim(owner), '') = ''")
print("empty_owner", c.fetchone()[0])
c.execute("select count(*) from registry_records where address is null or trim(address) = ''")
print("empty_address", c.fetchone()[0])
c.execute("select count(*) from registry_records where phones is null or trim(phones) = ''")
print("empty_phones", c.fetchone()[0])
c.execute("select count(*) from registry_records where accepts_external_waste")
print("accepts_true", c.fetchone()[0])
c.execute("select count(*) from registry_records where not accepts_external_waste")
print("accepts_false", c.fetchone()[0])
conn.close()
