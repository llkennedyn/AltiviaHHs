"""Real Graph administration smoke test; writes ONLY isolated HH_TEST_ lists."""
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
from sharepoint_graph import Graph, resolve_site
from sharepoint_store import Store
from db_sharepoint import Engine
from admin_ops import create_collaborator, reset_password, replace_assignments, set_project_status


def main():
    graph=Graph();site=resolve_site(graph);prefix='HH_TEST_'
    store=Store(graph,site,prefix);engine=Engine(store)
    nonce=secrets.token_hex(6);ids=[];project=None
    try:
        with engine.begin() as c:
            actor=c.execute(text("INSERT INTO users(username,name,pw,role,active) VALUES(:username,'Synthetic admin smoke',:pw,'admin',1) RETURNING id"),dict(username=f'qadmin_{nonce}',pw=generate_password_hash(secrets.token_urlsafe(24)))).scalar_one()
            ids.append(actor)
            project=c.execute(text("INSERT INTO projects(code,name,supervisor_id) VALUES(:code,'Synthetic administration test',:actor) RETURNING id"),dict(code=f'QADMIN-{nonce}',actor=actor)).scalar_one()
            a=c.execute(text("INSERT INTO activities(project_id,code,name,budget_quarters) VALUES(:pid,'A','Synthetic activity A',400) RETURNING id"),dict(pid=project)).scalar_one()
            b=c.execute(text("INSERT INTO activities(project_id,code,name,budget_quarters) VALUES(:pid,'B','Synthetic activity B',200) RETURNING id"),dict(pid=project)).scalar_one()
            created=create_collaborator(c,actor,f'qperson{nonce}','Paz','Synthetic')
            worker=created['id'];ids.append(worker)
            c.execute(text('INSERT INTO assignments(user_id,project_id) VALUES(:uid,:pid)'),dict(uid=worker,pid=project))
            c.execute(text('INSERT INTO activity_assignments(user_id,activity_id,planned_quarters) VALUES(:uid,:aid,77)'),dict(uid=worker,aid=a))
            entry=c.execute(text("INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,submission_key) VALUES(:uid,:aid,'2026-10-10',4,'Synthetic administration smoke hours','aprobado',:key) RETURNING id"),dict(uid=worker,aid=a,key=f'admin-smoke-{nonce}')).scalar_one()
        with engine.begin() as c:replace_assignments(c,actor,worker,project,[a,b],[a],True,True)
        with engine.begin() as c:
            assert c.execute(text('SELECT planned_quarters FROM activity_assignments WHERE user_id=:uid AND activity_id=:aid'),dict(uid=worker,aid=a)).scalar()==77
            replace_assignments(c,actor,worker,project,[b],[a,b],True,True)
            reset_password(c,actor,worker,'synthetic6')
            set_project_status(c,actor,project,'terminado','activo')
        # Cold read from Graph, independent of the writer's cache.
        data=Store(graph,site,prefix).snapshot()['data']
        assert data['projects'][str(project)]['status']=='terminado'
        assert data['entries'][str(entry)]['quarters']==4
        assert data['activities'][str(a)]['budget_quarters']==400
        assert data['users'][str(worker)]['must_change_pw']==1
        assert check_password_hash(data['users'][str(worker)]['pw'],'synthetic6')
        assigned={r['activity_id'] for r in data['activity_assignments'].values() if r['user_id']==worker}
        assert assigned=={b}
        print(f'PASS: run {nonce}; HH_TEST_ only; create/reset/assignment edit/project finish/cold read/history and budgets preserved.')
    finally:
        if ids:
            with engine.begin() as c:
                for uid in ids:c.execute(text('UPDATE users SET active=0 WHERE id=:uid'),{'uid':uid})
            print('Synthetic test accounts deactivated; retained for audit. Production HH_ lists were not written.')


if __name__=='__main__':main()
