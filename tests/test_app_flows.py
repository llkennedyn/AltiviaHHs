from pathlib import Path
import ast
import re

import pytest
from streamlit.testing.v1 import AppTest
import db_sharepoint
from db_sharepoint import memory_db, sqlite_sql
from test_sharepoint import setup


def test_static_sql_compiles(setup):
    _, s, _ = setup
    c = memory_db(s.snapshot())
    source = ast.parse(Path('app.py').read_text(encoding='utf-8'))
    checked = 0
    for node in ast.walk(source):
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            sql = node.value.strip()
            if not re.match(r'^(SELECT|INSERT|UPDATE|DELETE)\s',sql): continue
            if sql.endswith(('WHERE','FROM','SET','+')) or sql in ('SELECT * FROM projects WHERE',): continue
            try:
                c.execute('EXPLAIN '+sqlite_sql(sql),{k:1 for k in re.findall(r'(?<!:):([a-zA-Z_]\w*)',sql)})
            except Exception:
                # Concatenated fragments are checked by the UI flow tests below.
                if isinstance(getattr(node,'parent',None),ast.BinOp): continue
                raise
            checked += 1
    assert checked > 30


@pytest.mark.parametrize('uid,expected',[(1,10),(2,5),(3,2)])
def test_all_role_pages_render(setup,monkeypatch,uid,expected):
    _, _, e = setup
    monkeypatch.setattr(db_sharepoint,'_engine',e)
    monkeypatch.setenv('DATA_BACKEND','sharepoint')
    at=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    at.session_state['uid']=uid
    at.run()
    assert not at.exception
    pages=at.sidebar.radio[0].options
    assert len(pages)==expected
    for page in pages:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, (page,list(at.exception))
