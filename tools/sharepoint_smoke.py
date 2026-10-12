"""Real integration test. Writes synthetic data ONLY to HH_TEST_ lists."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db_sharepoint import Engine
from sharepoint_graph import Graph, resolve_site
from sharepoint_store import Store, TABLES, Conflict, provision


def main():
    g=Graph(); site=resolve_site(g)
    s=Store(g,site,'HH_TEST_')
    provision(s)
    e=Engine(s)
    run=uuid.uuid4().hex[:12]
    with e.begin() as c:
        uid=c.execute("INSERT INTO users(username,name,pw,role,active) VALUES(:n,'Synthetic integration test',:p,'trabajador',0) RETURNING id",dict(n='test_'+run,p=uuid.uuid4().hex)).scalar_one()
        pid=c.execute("INSERT INTO projects(code,name) VALUES(:c,'Synthetic integration test') RETURNING id",{'c':run}).scalar_one()
        aid=c.execute("INSERT INTO activities(project_id,code,name,budget_quarters) VALUES(:p,'TEST','Synthetic',400) RETURNING id",{'p':pid}).scalar_one()
        c.execute('INSERT INTO rates(user_id,rate_cents) VALUES(:u,2500)',{'u':uid})
        eid=c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,approval_at) VALUES(:u,:a,'2026-10-01',5,'Synthetic integration test','aprobado','2026-10-02 10:00:00') RETURNING id",{'u':uid,'a':aid}).scalar_one()
    cold=Store(g,site,'HH_TEST_').snapshot()
    assert cold['data']['entries'][str(eid)]['quarters']==5
    with e.begin() as c:
        lid=c.execute("INSERT INTO liquidations(user_id,period,cutoff_date,cents,quarters) VALUES(:u,'TEST','2026-10-02',3125,5) RETURNING id",{'u':uid}).scalar_one()
        c.execute('INSERT INTO liquidation_lines(liquidation_id,entry_id,quarters,rate_cents,amount_cents) VALUES(:l,:e,5,2500,3125)',{'l':lid,'e':eid})
        c.execute("UPDATE entries SET state='liquidado',liquidation_id=:l WHERE id=:e",{'l':lid,'e':eid})
    after=Store(g,site,'HH_TEST_').snapshot()
    assert after['data']['entries'][str(eid)]['liquidation_id']==lid
    assert after['data']['liquidations'][str(lid)]['cents']==3125
    # A stale reader cannot overwrite the finalized liquidation.
    try:
        stale=Store(g,site,'HH_TEST_')
        changed={t:dict(rows) for t,rows in cold['data'].items()}
        changed['projects'][str(pid)]={**changed['projects'][str(pid)],'name':'must not persist'}
        stale.commit(cold,changed,cold['sequences'])
        raise AssertionError('Concurrent write was incorrectly accepted')
    except Conflict: pass
    # Exercise Graph's actual If-Match check without changing the current value.
    control=after['control']
    from sharepoint_graph import GraphError
    try:
        g.request('PATCH',s.path('_control')+'/'+control['id']+'/fields',{'Head':after['head']},{'If-Match':cold['control']['eTag']})
        raise AssertionError('Graph accepted a stale ETag')
    except GraphError as ex:
        assert ex.status==412,ex.status
    print('PASS: authentication, lists, cold read, atomic liquidation, stale-write rejection, Graph ETag 412.')
    print('Synthetic run retained for audit:',run)


if __name__=='__main__': main()
