import copy
import json
import re
from urllib.parse import unquote

import pytest
from db_sharepoint import Engine, reset_context
from sharepoint_graph import GraphError
from sharepoint_store import Store, TABLES, Conflict, IntegrityError


class FakeGraph:
    """Fault-injectable Graph contract, independent of the SQL adapter."""
    def __init__(self):
        self.rows = {t: {} for t in [*TABLES, '_control', '_commits']}
        self.rows['_control']['1'] = dict(id='1', eTag='1', fields=dict(Key='root', SchemaVersion='1', Head=''))
        self.failure = None
        self.lost_response = False

    def pages(self, path):
        table = path.split('/lists/')[1].split('/')[0]
        rows = list(self.rows[table].values())
        if '$filter=' in path:
            key = unquote(path.split('$filter=')[1]).split("'")[1]
            rows = [r for r in rows if r['fields']['Key'] == key]
        yield from copy.deepcopy(rows)

    def request(self, method, path, body=None, headers=None):
        table, suffix = path.split('/lists/')[1].split('/items', 1)
        if method == 'GET':
            return copy.deepcopy(self.rows[table][suffix.split('?')[0].strip('/')])
        if self.failure == table:
            raise GraphError(503)
        if method == 'POST':
            if any(r['fields']['Key'] == body['fields']['Key'] for r in self.rows[table].values()):
                raise GraphError(409)
            rid = str(len(self.rows[table]) + 1)
            row = dict(id=rid, eTag='1', fields=copy.deepcopy(body['fields']))
            self.rows[table][rid] = row
            return copy.deepcopy(row)
        assert method == 'PATCH' and table == '_control'
        row = self.rows[table]['1']
        if headers['If-Match'] != row['eTag']:
            raise GraphError(412)
        row['fields'].update(body)
        row['eTag'] = str(int(row['eTag']) + 1)
        if self.lost_response:
            raise GraphError(0)
        return copy.deepcopy(row['fields'])


def store(graph):
    s = Store(graph, 'test')
    s.lists = {t: t for t in graph.rows}
    return s


@pytest.fixture
def setup():
    g = FakeGraph()
    s = store(g)
    e = Engine(s)
    reset_context()
    with e.begin() as c:
        for name, role in [('admin','admin'), ('supervisor','supervisor'), ('worker','trabajador')]:
            c.execute('INSERT INTO users(username,name,pw,role) VALUES(:n,:n,:p,:r)',dict(n=name,p='synthetic',r=role))
        c.execute("INSERT INTO projects(code,name,supervisor_id) VALUES('TEST','Synthetic',2)")
        c.execute("INSERT INTO activities(project_id,code,name,budget_quarters) VALUES(1,'A','Test',400)")
        c.execute('INSERT INTO rates(user_id,rate_cents) VALUES(3,2500)')
    return g, s, e


def test_atomic_failure_and_recovery(setup):
    g, s, e = setup
    original = s.snapshot()
    g.failure = '_commits'
    with pytest.raises(GraphError):
        with e.begin() as c:
            c.execute("UPDATE projects SET name='invisible'")
    assert store(g).snapshot()['data'] == original['data']
    g.failure = None
    g.lost_response = True
    with e.begin() as c:
        c.execute("UPDATE projects SET name='visible'")
    assert store(g).snapshot()['data']['projects']['1']['name'] == 'visible'


def test_competing_writers_cannot_overwrite(setup):
    g, s, e = setup
    other = store(g)
    stale = other.snapshot()
    with e.begin() as c:
        c.execute("UPDATE projects SET name='winner'")
    modified = copy.deepcopy(stale['data'])
    modified['projects']['1']['name'] = 'loser'
    with pytest.raises(Conflict):
        other.commit(stale, modified, stale['sequences'])
    assert store(g).snapshot()['data']['projects']['1']['name'] == 'winner'


def test_constraints_and_daily_limit(setup):
    g, s, e = setup
    with e.begin() as c:
        c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description) VALUES(3,1,'2026-10-10',40,'test')")
    with pytest.raises(ValueError, match='12 HH'):
        with e.begin() as c:
            c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description) VALUES(3,1,'2026-10-10',12,'test')")
    with pytest.raises(ValueError):
        with e.begin() as c:
            c.execute('INSERT INTO assignments(user_id,project_id) VALUES(999,1)')
    assert len(store(g).snapshot()['data']['entries']) == 1


def test_liquidation_roundtrip_and_frozen_rate(setup):
    g, s, e = setup
    with e.begin() as c:
        c.execute("INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,approval_at) VALUES(3,1,'2026-10-10',5,'test','aprobado','2026-10-11 10:00:00')")
    with e.begin() as c:
        rows = c.execute("SELECT * FROM entries WHERE state='aprobado' AND approval_at::date<=:cutoff FOR UPDATE",{'cutoff':'2026-10-11'}).all()
        assert len(rows) == 1
        lid = c.execute("INSERT INTO liquidations(user_id,period,cutoff_date,cents,quarters,created_by) VALUES(3,'2026-10','2026-10-11',3125,5,1) RETURNING id").scalar_one()
        c.execute('INSERT INTO liquidation_lines(liquidation_id,entry_id,quarters,rate_cents,amount_cents) VALUES(:l,1,5,2500,3125)',{'l':lid})
        c.execute("UPDATE entries SET state='liquidado',liquidation_id=:l WHERE id=1",{'l':lid})
    with e.begin() as c:
        c.execute('UPDATE rates SET rate_cents=5000 WHERE user_id=3')
    data = store(g).snapshot()['data']
    assert data['entries']['1']['state'] == 'liquidado'
    assert data['liquidation_lines']['1']['amount_cents'] == 3125
    assert data['liquidation_lines']['1']['rate_cents'] == 2500


def test_large_import_and_tamper_detection(setup):
    g, s, e = setup
    with e.begin() as c:
        for n in range(800):
            c.execute('INSERT INTO activities(project_id,code,name) VALUES(1,:c,:c)', {'c':f'B{n}'})
    assert len(store(g).snapshot()['data']['activities']) == 801
    latest = next(reversed(g.rows['activities'].values()))
    payload = json.loads(latest['fields']['Payload'])
    payload['name'] = 'tampered'
    latest['fields']['Payload'] = json.dumps(payload)
    with pytest.raises(IntegrityError):
        store(g).snapshot()
