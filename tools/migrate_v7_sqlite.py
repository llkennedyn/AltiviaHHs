"""One-time migration from a *COPY* of v7 SQLite to PostgreSQL.
Usage: python tools/migrate_v7_sqlite.py C:/ruta/altivia_hh.db
DATABASE_URL must target an EMPTY dedicated PostgreSQL database. Back up both ends.
"""
import sys, os, sqlite3
from pathlib import Path
from datetime import datetime,date
from sqlalchemy import text
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db import engine,init_schema

if len(sys.argv)!=2:raise SystemExit('Uso: python tools/migrate_v7_sqlite.py ruta_a_copia_altivia_hh.db')
source=Path(sys.argv[1])
if not source.is_file():raise SystemExit('No existe archivo fuente.')
init_schema()
s=sqlite3.connect(f'file:{source}?mode=ro',uri=True);s.row_factory=sqlite3.Row

def table_exists(n):return bool(s.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(n,)).fetchone())
def rows(n):return [dict(r) for r in s.execute(f'SELECT * FROM {n}')] if table_exists(n) else []
def columns(n):return {r[1] for r in s.execute(f'PRAGMA table_info({n})')}
def safe_datetime(v):return v or datetime.utcnow().isoformat()
with engine().begin() as c:
    if c.execute(text('SELECT COUNT(*) FROM users')).scalar():raise SystemExit('La base destino no está vacía. Usa una base PostgreSQL nueva.')
    for r in rows('users'):
        c.execute(text('INSERT INTO users(id,username,name,pw,role,active,must_change_pw) VALUES(:id,:username,:name,:pw,:role,:active,:must_change_pw)'),dict(id=r['id'],username=r['username'],name=r['name'],pw=r['pw'],role=r['role'],active=r['active'],must_change_pw=r.get('must_change_pw',0)))
    for r in rows('projects'):
        status=r.get('status') or ('activo' if r.get('active',1) else 'desactivado')
        c.execute(text('INSERT INTO projects(id,code,name,status,supervisor_id) VALUES(:id,:code,:name,:status,:supervisor_id)'),dict(id=r['id'],code=r['code'],name=r['name'],status=status,supervisor_id=r.get('supervisor_id')))
    for r in rows('activities'):
        c.execute(text('INSERT INTO activities(id,project_id,code,name,budget_quarters,active) VALUES(:id,:project_id,:code,:name,:budget_quarters,:active)'),dict(id=r['id'],project_id=r['project_id'],code=r['code'],name=r['name'],budget_quarters=r.get('budget_quarters',0),active=r.get('active',1)))
    for t,fields in [('assignments',['user_id','project_id']),('activity_assignments',['user_id','activity_id','planned_quarters'])]:
        for r in rows(t):
            c.execute(text(f"INSERT INTO {t} ({','.join(fields)}) VALUES ({','.join(':'+x for x in fields)})"),{f:r[f] for f in fields})
    # v7 has dated tariffs; use the most recent as the editable standard tariff.
    latest={}
    for r in sorted(rows('rates'),key=lambda x:(x['effective_date'],x['id'])):latest[r['user_id']]=r['rate_cents']
    for uid,rate in latest.items():c.execute(text('INSERT INTO rates(user_id,rate_cents) VALUES(:u,:r)'),dict(u=uid,r=rate))
    for r in rows('liquidations'):
        cut=r.get('cutoff_date') or r['period']+'-01'
        c.execute(text('''INSERT INTO liquidations(id,user_id,period,cutoff_date,cents,quarters,created_at,created_by)
        VALUES(:id,:user_id,:period,:cutoff_date,:cents,:quarters,:created_at,:created_by)'''),dict(id=r['id'],user_id=r['user_id'],period=r['period'],cutoff_date=cut,cents=r['cents'],quarters=r['quarters'],created_at=safe_datetime(r['created_at']),created_by=r.get('created_by')))
    for r in rows('entries'):
        c.execute(text('''INSERT INTO entries(id,user_id,activity_id,work_date,quarters,description,state,note,created_at,updated_at,approval_by,approval_at,liquidation_id,submission_key)
        VALUES(:id,:user_id,:activity_id,:work_date,:quarters,:description,:state,:note,:created_at,:updated_at,:approval_by,:approval_at,:liquidation_id,:submission_key)'''),dict(id=r['id'],user_id=r['user_id'],activity_id=r['activity_id'],work_date=r['work_date'],quarters=r['quarters'],description=r['description'],state=r['state'],note=r.get('note') or '',created_at=safe_datetime(r['created_at']),updated_at=safe_datetime(r['updated_at']),approval_by=r.get('approval_by'),approval_at=r.get('approval_at'),liquidation_id=r.get('liquidation_id'),submission_key=r.get('submission_key')))
    for r in rows('liquidation_lines'):
        c.execute(text('INSERT INTO liquidation_lines(id,liquidation_id,entry_id,quarters,rate_cents,amount_cents) VALUES(:id,:liquidation_id,:entry_id,:quarters,:rate_cents,:amount_cents)'),r)
    for r in rows('audit'):
        c.execute(text('INSERT INTO audit(id,actor_id,action,target,target_id,detail,at) VALUES(:id,:actor_id,:action,:target,:target_id,:detail,:at)'),r)
    for r in rows('import_log'):
        c.execute(text('INSERT INTO import_log(id,project_id,filename,processed_at,actor_id,notes) VALUES(:id,:project_id,:filename,:processed_at,:actor_id,:notes)'),r)
    for table in ('users','projects','activities','rates','entries','liquidations','liquidation_lines','audit','import_log'):
        c.execute(text('SELECT setval(pg_get_serial_sequence(:table,\'id\'),COALESCE((SELECT max(id) FROM '+table+'),1), (SELECT COUNT(*)>0 FROM '+table+'))'),{'table':table})
s.close()
print('Migración completa: usuarios, proyectos, actividades, asignaciones, registros, liquidaciones, historial y tarifas estándar.')
print('REVISAR: las tarifas históricas se consolidaron en tarifa estándar (última); las liquidaciones anteriores conservan sus líneas originales.')
