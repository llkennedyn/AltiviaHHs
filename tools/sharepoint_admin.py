"""Explicit backup, validation and empty-target migration; never delete data."""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sharepoint_graph import Graph, resolve_site, setting
from sharepoint_store import Store, TABLES, row_key, digest, provision
from db_sharepoint import memory_db


def write_backup(path, snapshot):
    payload = {'schema': 1, 'data': snapshot['data'], 'sequences': snapshot['sequences']}
    document = {'payload': payload, 'sha256': digest(payload)}
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(document, f, ensure_ascii=False, indent=2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['check', 'provision', 'backup', 'export-postgres', 'import-empty'])
    p.add_argument('--file')
    args = p.parse_args()
    if args.action == 'export-postgres':
        from db_postgres import engine
        from sqlalchemy import text
        with engine().connect().execution_options(isolation_level='REPEATABLE READ') as c:
            with c.begin():
                c.execute(text('SET TRANSACTION READ ONLY'))
                data = {}
                for t in TABLES:
                    rows = [dict(r) for r in c.execute(text('SELECT * FROM ' + t)).mappings()]
                    for r in rows:
                        for k,v in r.items():
                            if isinstance(v,(date,datetime)): r[k] = v.isoformat(sep=' ') if isinstance(v,datetime) else v.isoformat()
                    data[t] = {row_key(t,r): r for r in rows}
                seq = {t:max((int(r['id']) for r in data[t].values()),default=0) for t in TABLES if TABLES[t][1] == ('id',)}
        write_backup(args.file, {'data':data,'sequences':seq})
        print('Respaldo de PostgreSQL creado sin modificar el origen.');return
    g=Graph(); s=Store(g,resolve_site(g),setting('SP_LIST_PREFIX','HH_'))
    if args.action == 'provision':
        provision(s)
    before=s.snapshot()
    if args.action == 'backup':
        write_backup(args.file,before)
    elif args.action == 'import-empty':
        if any(before['data'].values()): raise RuntimeError('Destino no vacío: importación cancelada.')
        document=json.loads(Path(args.file).read_text(encoding='utf-8'))
        payload=document['payload']
        if payload.get('schema') != 1 or document['sha256'] != digest(payload):
            raise RuntimeError('Respaldo incompatible o modificado.')
        if set(payload['data']) != set(TABLES): raise RuntimeError('Tablas incompletas.')
        memory_db(payload).close()
        s.commit(before,payload['data'],payload['sequences'])
        s.cache=None
        if s.snapshot()['data'] != payload['data']: raise RuntimeError('Verificación de migración falló.')
    print(json.dumps({t:len(rows) for t,rows in s.snapshot()['data'].items()}))


if __name__ == '__main__': main()
