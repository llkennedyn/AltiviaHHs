"""Durable storage selection. PostgreSQL retained for rollback/migration."""
from sharepoint_graph import setting
BACKEND = setting('DATA_BACKEND', 'sharepoint').lower()
if BACKEND == 'sharepoint':
    from db_sharepoint import engine, init_schema, one, all_rows, scalar, exec_sql, add, log, reset_context
elif BACKEND == 'postgresql':
    from db_postgres import engine, init_schema, one, all_rows, scalar, exec_sql, add, log
    def reset_context():
        pass
else:
    raise RuntimeError('DATA_BACKEND debe ser sharepoint o postgresql.')
from db_postgres import SCHEMA
