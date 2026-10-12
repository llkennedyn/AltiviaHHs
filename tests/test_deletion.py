import copy
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
import db_sharepoint
from test_sharepoint import setup
from admin_ops import delete_user, delete_project, restore_user, restore_project, reset_password, replace_assignments, set_project_status


def test_deletion_preserves_history_and_restores_inactive(setup):
    _, store, engine=setup
    with engine.begin() as c:
        c.execute('INSERT INTO assignments(user_id,project_id) VALUES(3,1)')
        c.execute('INSERT INTO activity_assignments(user_id,activity_id,planned_quarters) VALUES(3,1,77)')
        c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,submission_key) VALUES(3,1,'2026-10-10',4,'Historical work','aprobado','delete-history')")
    before=copy.deepcopy(store.snapshot()['data'])
    with engine.begin() as c:
        delete_user(c,1,3)
        delete_project(c,1,1)
    data=store.snapshot()['data']
    assert data['users']['3']['deleted']==1 and data['users']['3']['active']==0
    assert data['projects']['1']['deleted']==1 and data['projects']['1']['status']=='desactivado'
    for table in ('entries','activities','assignments','activity_assignments','rates','liquidations','liquidation_lines'):
        assert data[table]==before[table]
    for operation in (lambda c:reset_password(c,1,3,'nuevo6'),lambda c:replace_assignments(c,1,3,1,[1],[1]),lambda c:set_project_status(c,1,1,'activo','desactivado')):
        with pytest.raises(ValueError):
            with engine.begin() as c:operation(c)
    with engine.begin() as c:
        restore_user(c,1,3)
        restore_project(c,1,1)
    data=store.snapshot()['data']
    assert data['users']['3']['deleted']==0 and data['users']['3']['active']==0
    assert data['projects']['1']['deleted']==0 and data['projects']['1']['status']=='desactivado'


def test_delete_requires_admin_and_cannot_delete_self(setup):
    _, _, engine=setup
    for operation in (lambda c:delete_user(c,3,2),lambda c:delete_project(c,3,1),lambda c:restore_user(c,3,2),lambda c:restore_project(c,3,1),lambda c:delete_user(c,1,1)):
        with pytest.raises(ValueError):
            with engine.begin() as c:operation(c)


def test_old_sharepoint_rows_load_without_deleted_field(setup):
    _, store, _=setup
    snapshot=copy.deepcopy(store.snapshot())
    for table in ('users','projects'):
        for row in snapshot['data'][table].values():row.pop('deleted',None)
    c=db_sharepoint.memory_db(snapshot)
    assert c.execute('SELECT COUNT(*) FROM users WHERE deleted=0').fetchone()[0]==3
    assert c.execute('SELECT COUNT(*) FROM projects WHERE deleted=0').fetchone()[0]==1
    c.close()


def test_admin_delete_confirmations_and_worker_session_revocation(setup,monkeypatch):
    _, store, engine=setup
    monkeypatch.setattr(db_sharepoint,'_engine',engine)
    monkeypatch.setenv('DATA_BACKEND','sharepoint')
    admin=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    admin.session_state['uid']=1
    admin.run().sidebar.radio[0].set_value('Usuarios y tarifas').run()
    target=next(s for s in admin.selectbox if s.label=='Usuario a eliminar')
    target.select_index(1).run()
    assert next(b for b in admin.button if b.label=='Eliminar usuario').disabled
    worker=AppTest.from_file(Path('app.py').resolve(),default_timeout=20)
    worker.session_state['uid']=3
    worker.run()
    next(c for c in admin.checkbox if c.key=='delete_user_confirm_3').check().run()
    next(b for b in admin.button if b.label=='Eliminar usuario').click().run()
    assert not admin.exception and store.snapshot()['data']['users']['3']['deleted']==1
    worker.run()
    assert not worker.exception and any(b.label=='Ingresar' for b in worker.button)
    assert not worker.sidebar.radio
    next(b for b in admin.button if b.label=='Recuperar usuario').click().run()
    assert store.snapshot()['data']['users']['3']['active']==0
    admin.sidebar.radio[0].set_value('Proyectos y actividades').run()
    assert next(b for b in admin.button if b.label=='Eliminar proyecto').disabled
    next(c for c in admin.checkbox if c.key=='delete_project_confirm_1').check().run()
    next(b for b in admin.button if b.label=='Eliminar proyecto').click().run()
    assert not admin.exception and store.snapshot()['data']['projects']['1']['deleted']==1
    assert not any(b.label=='Guardar proyecto' for b in admin.button)
    next(b for b in admin.button if b.label=='Recuperar proyecto').click().run()
    assert not admin.exception and store.snapshot()['data']['projects']['1']['status']=='desactivado'
