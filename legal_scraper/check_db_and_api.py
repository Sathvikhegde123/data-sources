import json
from load_property_rights_postgres import PROPERTY_RIGHTS_DIR, build_dsn
print('PROPERTY_RIGHTS_DIR =>', PROPERTY_RIGHTS_DIR)
import psycopg2
from urllib import request

dsn = build_dsn()
print('DSN summary =>', ' '.join(dsn.split()[:3]))
try:
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM documents WHERE document_type='case';")
            print('documents(case) count =>', cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM case_metadata;")
            print('case_metadata rows =>', cur.fetchone()[0])
            cur.execute("SELECT d.id,d.title,m.citation,m.date_of_judgment FROM documents d JOIN case_metadata m ON m.document_id=d.id ORDER BY d.id DESC LIMIT 5;")
            rows = cur.fetchall()
            print('recent 5 cases:')
            for r in rows:
                print(r)
except Exception as e:
    print('DB CHECK ERROR:', e)

# backend API
try:
    url = 'http://localhost:8000/api/cases'
    print('\nRequesting', url)
    resp = request.urlopen(url, timeout=10)
    data = resp.read().decode('utf-8')
    print('API /api/cases response (first 1000 chars):')
    print(data[:1000])
except Exception as e:
    print('API CHECK ERROR:', e)
