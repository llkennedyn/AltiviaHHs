from pathlib import Path
import ast
import re

import pytest
from streamlit.testing.v1 import AppTest
import db_sharepoint
import db
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


def test_worker_submission_and_supervisor_approval(setup,monkeypatch):
    _, s, e = setup
    monkeypatch.setattr(db_sharepoint,'_engine',e)
    monkeypatch.setenv('DATA_BACKEND','sharepoint')
    with e.begin() as c:
        c.execute('INSERT INTO assignments(user_id,project_id) VALUES(3,1)')
        c.execute('INSERT INTO activity_assignments(user_id,activity_id,planned_quarters) VALUES(3,1,40)')
    worker=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    worker.session_state['uid']=3
    worker.run().sidebar.radio[0].set_value('Registrar horas').run()
    worker.text_area[0].set_value('Synthetic engineering work')
    worker.number_input[0].set_value(1.25)
    next(b for b in worker.button if b.label=='Enviar para aprobación').click().run()
    assert not worker.exception and not worker.error
    assert s.snapshot()['data']['entries']['1']['state']=='pendiente'
    reviewer=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    reviewer.session_state['uid']=2
    reviewer.run().sidebar.radio[0].set_value('Aprobaciones').run()
    next(b for b in reviewer.button if b.label=='Registrar decisión').click().run()
    assert not reviewer.exception and not reviewer.error
    entry=s.snapshot()['data']['entries']['1']
    assert entry['state']=='aprobado' and entry['approval_by']==2 and entry['quarters']==5
    reviewer.sidebar.radio[0].set_value('Presupuestos EDT').run()
    table=reviewer.dataframe[0].value
    assert table.iloc[0]['Presupuesto_HH']==100
    assert table.iloc[0]['HH_cargadas']==1.25


def test_dashboard_shortcut_and_project_responsible_preserved(setup,monkeypatch):
    _, s, e = setup
    monkeypatch.setattr(db_sharepoint,'_engine',e)
    monkeypatch.setenv('DATA_BACKEND','sharepoint')
    at=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    at.session_state['uid']=1
    at.run()
    next(b for b in at.button if b.label=='Ir a aprobaciones →').click().run()
    assert not at.exception and at.sidebar.radio[0].value=='Aprobaciones'
    at.sidebar.radio[0].set_value('Proyectos y actividades').run()
    # Saving a project's name must retain the responsible supervisor selected by default.
    next(t for t in at.text_input if t.label=='Nombre' and t.value=='Synthetic').set_value('Renamed project')
    next(b for b in at.button if b.label=='Guardar proyecto').click().run()
    assert not at.exception and not at.error
    project=s.snapshot()['data']['projects']['1']
    assert project['name']=='Renamed project' and project['supervisor_id']==2


def test_worker_privacy_and_personal_history(setup,monkeypatch):
    _, _, e = setup
    monkeypatch.setattr(db_sharepoint,'_engine',e)
    monkeypatch.setenv('DATA_BACKEND','sharepoint')
    with e.begin() as c:
        c.execute('INSERT INTO assignments(user_id,project_id) VALUES(3,1)')
        c.execute('INSERT INTO activity_assignments(user_id,activity_id,planned_quarters) VALUES(3,1,40)')
        c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,submission_key) VALUES(3,1,'2026-10-10',4,'My own work','pendiente','own')")
        c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,submission_key) VALUES(2,1,'2026-10-10',8,'Private colleague work','aprobado','colleague')")
    original=db.all_rows
    def private_reads(sql,args=None):
        assert not re.search(r'budget_quarters|planned_quarters|\brates\b|\bliquidations\b',str(sql),re.I), sql
        return original(sql,args)
    monkeypatch.setattr(db,'all_rows',private_reads)
    at=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    at.session_state['uid']=3
    # A stale or forged manager page must never render or read projected budgets.
    at.session_state['navigation']='Centro gerencial'
    at.run()
    assert not at.exception
    assert [label.split('  ',1)[-1] for label in at.sidebar.radio[0].options]==['Registrar horas','Mi historial']
    assert at.sidebar.radio[0].value=='Registrar horas'
    assert not at.metric and not at.dataframe
    at.sidebar.radio[0].set_value('Mi historial').run()
    assert not at.exception
    table=at.dataframe[0].value
    assert len(table)==1 and table.iloc[0]['Descripción']=='My own work'
    assert table.iloc[0]['Estado']=='Pendiente'
    assert not any('presupuesto' in str(column).lower() or 'tarifa' in str(column).lower() for column in table.columns)
    next(x for x in at.selectbox if x.label=='Estado de mis horas').set_value('Aprobado').run()
    assert not at.dataframe and not at.exception


def test_worker_corrects_observed_hours_from_history(setup,monkeypatch):
    _, s, e = setup
    monkeypatch.setattr(db_sharepoint,'_engine',e)
    monkeypatch.setenv('DATA_BACKEND','sharepoint')
    with e.begin() as c:
        c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,note,submission_key) VALUES(3,1,'2026-10-10',4,'Original work','observado','Please clarify','observed')")
    at=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    at.session_state['uid']=3
    at.run().sidebar.radio[0].set_value('Mi historial').run()
    next(x for x in at.text_area if x.label=='Descripción corregida').set_value('Clarified work')
    next(x for x in at.button if x.label=='Reenviar').click().run()
    assert not at.exception and not at.error
    entry=s.snapshot()['data']['entries']['1']
    assert entry['state']=='pendiente' and entry['description']=='Clarified work'
