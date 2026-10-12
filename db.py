"""Transactional data access for ALTIVIA Streamlit. PostgreSQL is required."""
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

_engine=None

def engine():
    global _engine
    if _engine is None:
        url=os.environ.get('DATABASE_URL','').strip()
        if not url:
            try:
                import streamlit as st
                url=st.secrets.get('DATABASE_URL','')
            except Exception: pass
        if not url:
            raise RuntimeError('Configura DATABASE_URL con PostgreSQL persistente en Streamlit Secrets.')
        if url.startswith('postgres://'): url='postgresql://'+url[len('postgres://'):]
        if not url.startswith('postgresql://'):
            raise RuntimeError('Producción requiere PostgreSQL. SQLite no se admite en Streamlit Community Cloud.')
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        _engine=create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=1200)
    return _engine

def all_rows(sql,args=None):
    with engine().connect() as c:return [dict(r) for r in c.execute(text(sql),args or {}).mappings().all()]

def one(sql,args=None):
    with engine().connect() as c:
        r=c.execute(text(sql),args or {}).mappings().first()
        return dict(r) if r else None

def scalar(sql,args=None):
    with engine().connect() as c:return c.execute(text(sql),args or {}).scalar()

def exec_sql(sql,args=None):
    with engine().begin() as c:return c.execute(text(sql),args or {}).rowcount

def add(sql,args=None):
    with engine().begin() as c:return c.execute(text(sql),args or {}).scalar_one()

def log(c,actor,action,target,tid=None,detail=''):
    c.execute(text('INSERT INTO audit(actor_id,action,target,target_id,detail,at) VALUES(:actor,:action,:target,:tid,:detail,:at)'),dict(actor=actor,action=action,target=target,tid=tid,detail=str(detail)[:500],at=datetime.utcnow().isoformat()))

SCHEMA='''
CREATE TABLE IF NOT EXISTS users (id BIGSERIAL PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,pw TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','supervisor','trabajador')),active INTEGER NOT NULL DEFAULT 1,must_change_pw INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects (id BIGSERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'activo' CHECK(status IN ('activo','desactivado','terminado')),supervisor_id BIGINT REFERENCES users(id));
CREATE TABLE IF NOT EXISTS activities (id BIGSERIAL PRIMARY KEY,project_id BIGINT NOT NULL REFERENCES projects(id),code TEXT NOT NULL,name TEXT NOT NULL,budget_quarters BIGINT NOT NULL DEFAULT 0 CHECK(budget_quarters>=0),active INTEGER NOT NULL DEFAULT 1,UNIQUE(project_id,code));
CREATE TABLE IF NOT EXISTS assignments (user_id BIGINT REFERENCES users(id),project_id BIGINT REFERENCES projects(id),PRIMARY KEY(user_id,project_id));
CREATE TABLE IF NOT EXISTS activity_assignments (user_id BIGINT REFERENCES users(id),activity_id BIGINT REFERENCES activities(id),planned_quarters BIGINT NOT NULL DEFAULT 0,PRIMARY KEY(user_id,activity_id));
CREATE TABLE IF NOT EXISTS rates (id BIGSERIAL PRIMARY KEY,user_id BIGINT UNIQUE REFERENCES users(id),rate_cents BIGINT NOT NULL CHECK(rate_cents>=0));
CREATE TABLE IF NOT EXISTS entries (id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),activity_id BIGINT NOT NULL REFERENCES activities(id),work_date DATE NOT NULL,quarters INTEGER NOT NULL CHECK(quarters BETWEEN 1 AND 48),description TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pendiente' CHECK(state IN ('borrador','pendiente','observado','aprobado','rechazado','liquidado')),note TEXT NOT NULL DEFAULT '',created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,approval_by BIGINT REFERENCES users(id),approval_at TIMESTAMP,liquidation_id BIGINT,submission_key TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS liquidations (id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),period TEXT NOT NULL,cutoff_date DATE NOT NULL,cents BIGINT NOT NULL,quarters BIGINT NOT NULL,created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,created_by BIGINT REFERENCES users(id));
CREATE TABLE IF NOT EXISTS liquidation_lines (id BIGSERIAL PRIMARY KEY,liquidation_id BIGINT NOT NULL REFERENCES liquidations(id),entry_id BIGINT NOT NULL UNIQUE REFERENCES entries(id),quarters INTEGER NOT NULL,rate_cents BIGINT NOT NULL,amount_cents BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (id BIGSERIAL PRIMARY KEY,actor_id BIGINT,action TEXT NOT NULL,target TEXT NOT NULL,target_id BIGINT,detail TEXT,at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_log (id BIGSERIAL PRIMARY KEY,project_id BIGINT REFERENCES projects(id),filename TEXT,processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,actor_id BIGINT,notes TEXT);
CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(work_date);
CREATE INDEX IF NOT EXISTS idx_entries_user_state ON entries(user_id,state);
CREATE INDEX IF NOT EXISTS idx_entries_activity ON entries(activity_id);
CREATE INDEX IF NOT EXISTS idx_activities_project ON activities(project_id);
'''

def init_schema():
    with engine().begin() as c:
        for statement in SCHEMA.split(';'):
            if statement.strip():c.execute(text(statement))
