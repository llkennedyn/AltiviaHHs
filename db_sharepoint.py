"""In-memory relational queries; SharePoint Lists are the ONLY durable storage."""
import contextvars
import re
import sqlite3
from contextlib import contextmanager
from db_postgres import SCHEMA, log
from sharepoint_graph import Graph, resolve_site, setting
from sharepoint_store import Store, TABLES, row_key

_read_snapshot = contextvars.ContextVar('altivia_read_snapshot', default=None)
_engine = None

def reset_context():
    _read_snapshot.set(None)

def memory_db(snapshot):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA.replace('BIGSERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT'))
    for table, rows in snapshot['data'].items():
        for row in rows.values():
            columns = list(row)
            c.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', [row[k] for k in columns])
    for table, sequence in snapshot.get('sequences', {}).items():
        if table not in TABLES or TABLES[table][1] != ('id',):
            raise ValueError('Secuencia inválida.')
        c.execute('DELETE FROM sqlite_sequence WHERE name=?', (table,))
        c.execute('INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)', (table, int(sequence)))
    c.commit()
    c.execute('PRAGMA foreign_keys=ON')
    if c.execute('PRAGMA foreign_key_check').fetchone():
        c.close()
        raise RuntimeError('Referencias inválidas. Revisar respaldo.')
    for operation in ('INSERT', 'UPDATE'):
        c.executescript(f'''
        CREATE TRIGGER daily_limit_{operation.lower()} BEFORE {operation} ON entries
        WHEN NEW.state NOT IN ('rechazado','observado')
        BEGIN
          SELECT CASE WHEN NEW.quarters + COALESCE((SELECT SUM(quarters) FROM entries
            WHERE user_id=NEW.user_id AND work_date=NEW.work_date
            AND id<>NEW.id AND state NOT IN ('rechazado','observado')),0)>48
            THEN RAISE(ABORT,'La jornada no puede superar 12 HH.') END;
        END;''')
    return c

def sqlite_sql(statement):
    sql = re.sub(r'\bNOW\(\)', 'CURRENT_TIMESTAMP', str(statement), flags=re.I)
    sql = re.sub(r'\b([a-zA-Z_][\w.]*)::date', r'date(\1)', sql)
    sql = re.sub(r'\s+FOR UPDATE\b', '', sql, flags=re.I)
    return re.sub(r'\bUPDATE entries e\b', 'UPDATE entries AS e', sql, flags=re.I)

class Result:
    def __init__(self, cursor):
        self.rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
        self.rowcount = cursor.rowcount
    def mappings(self): return self
    def all(self): return self.rows
    def first(self): return self.rows[0] if self.rows else None
    def scalar(self): return next(iter(self.rows[0].values())) if self.rows else None
    def scalar_one(self):
        if len(self.rows) != 1: raise RuntimeError('Se esperaba exactamente un resultado.')
        return self.scalar()

class Connection:
    def __init__(self, connection, writable):
        self.connection, self.writable = connection, writable
    def execute(self, statement, args=None):
        sql = sqlite_sql(statement)
        if not self.writable and not sql.lstrip().upper().startswith('SELECT '):
            raise RuntimeError('La conexión de lectura no permite cambios.')
        try: return Result(self.connection.execute(sql, args or {}))
        except sqlite3.IntegrityError as exc: raise ValueError(str(exc)) from None

class Engine:
    def __init__(self, store): self.store = store
    @contextmanager
    def connect(self):
        snapshot = _read_snapshot.get()
        if snapshot is None or snapshot[0] is not self.store:
            snapshot = (self.store, self.store.snapshot())
            _read_snapshot.set(snapshot)
        connection = memory_db(snapshot[1])
        try: yield Connection(connection, False)
        finally: connection.close()
    @contextmanager
    def begin(self):
        snapshot = self.store.snapshot()
        connection = memory_db(snapshot)
        try:
            yield Connection(connection, True)
            if connection.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Referencias inválidas en la operación.')
            data = {t: {row_key(t, row): dict(row) for row in connection.execute('SELECT * FROM ' + t)} for t in TABLES}
            sequences = dict(connection.execute('SELECT name,seq FROM sqlite_sequence').fetchall())
            self.store.commit(snapshot, data, sequences)
            reset_context()
        finally: connection.close()

def engine():
    global _engine
    if _engine is None:
        graph = Graph()
        _engine = Engine(Store(graph, resolve_site(graph), setting('SP_LIST_PREFIX', 'HH_')))
    return _engine

def init_schema():
    # Runtime does not create lists: a separate administrator provisions them.
    with engine().connect() as c: c.execute('SELECT COUNT(*) FROM users')
def all_rows(sql, args=None):
    with engine().connect() as c: return c.execute(sql, args).all()
def one(sql, args=None):
    with engine().connect() as c: return c.execute(sql, args).first()
def scalar(sql, args=None):
    with engine().connect() as c: return c.execute(sql, args).scalar()
def exec_sql(sql, args=None):
    with engine().begin() as c: return c.execute(sql, args).rowcount
def add(sql, args=None):
    with engine().begin() as c: return c.execute(sql, args).scalar_one()
