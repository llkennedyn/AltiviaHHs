"""Append-only SharePoint Lists with an ETag-guarded commit pointer.

Rows written before the pointer swap are invisible to application readers.
An interrupted/conflicting commit leaves an unreachable revision, never partial
liquidations. Old rows are retained. Only the application may write these lists.
"""
import copy
import hashlib
import json
import threading
import uuid
from urllib.parse import quote

from sharepoint_graph import GraphError

TABLES = {
    'users': ('Usuarios', ('id',)),
    'projects': ('Proyectos', ('id',)),
    'activities': ('Actividades', ('id',)),
    'assignments': ('AsignacionesProyecto', ('user_id', 'project_id')),
    'activity_assignments': ('AsignacionesActividad', ('user_id', 'activity_id')),
    'rates': ('Tarifas', ('id',)),
    'entries': ('RegistrosHH', ('id',)),
    'liquidations': ('Liquidaciones', ('id',)),
    'liquidation_lines': ('DetalleLiquidaciones', ('id',)),
    'audit': ('Auditoria', ('id',)),
    'import_log': ('Importaciones', ('id',)),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def row_key(table, row):
    return ':'.join(str(row[k]) for k in TABLES[table][1])


class Conflict(RuntimeError):
    def __init__(self):
        super().__init__('Otra operación se confirmó mientras trabajabas. Actualiza y vuelve a intentarlo; tus cambios no se guardaron.')


class IntegrityError(RuntimeError):
    pass


class Store:
    def __init__(self, graph, site, prefix='HH_'):
        self.graph, self.site, self.prefix = graph, site, prefix
        self.lists = None
        self.cache = None
        self.lock = threading.RLock()

    def list_names(self):
        return {**{t: self.prefix + name for t, (name, _) in TABLES.items()},
                '_commits': self.prefix + 'Transacciones', '_control': self.prefix + 'Control'}

    def discover(self):
        found = {v['displayName']: v['id'] for v in self.graph.pages(f'/sites/{self.site}/lists?$select=id,displayName')}
        missing = [name for name in self.list_names().values() if name not in found]
        if missing:
            raise RuntimeError('Faltan listas de ALTIVIA. Ejecutar el aprovisionamiento autorizado.')
        self.lists = {t: found[name] for t, name in self.list_names().items()}

    def path(self, table):
        if self.lists is None:
            self.discover()
        return f'/sites/{self.site}/lists/{self.lists[table]}/items'

    def items(self, table):
        return self.graph.pages(self.path(table) + '?$expand=fields&$top=200')

    def item(self, table, item_id):
        return self.graph.request('GET', self.path(table) + '/' + quote(str(item_id), safe='') + '?$expand=fields')

    def unique(self, table, key):
        filt = quote("fields/Key eq '" + key.replace("'", "''") + "'", safe='')
        rows = list(self.graph.pages(self.path(table) + '?$expand=fields&$filter=' + filt))
        if len(rows) > 1:
            raise IntegrityError('Clave duplicada en SharePoint. No se puede continuar.')
        return rows[0] if rows else None

    def create_unique(self, table, fields):
        try:
            return self.graph.request('POST', self.path(table), {'fields': fields})
        except GraphError as exc:
            if exc.status not in (0, 409, 500, 502, 503, 504):
                raise
            existing = self.unique(table, fields['Key'])
            if existing and all(existing['fields'].get(k) == v for k, v in fields.items()):
                return existing
            raise

    def control(self):
        item = self.unique('_control', 'root')
        if not item or item['fields'].get('SchemaVersion') != '1':
            raise IntegrityError('Control de SharePoint ausente o incompatible.')
        if not item.get('eTag'):
            raise IntegrityError('SharePoint no devolvió la versión del control.')
        return item

    def _manifest(self, item):
        fields = item['fields']
        payload = json.loads(fields['Payload'])
        if fields['Key'] != payload['tx'] or fields['Digest'] != digest(payload):
            raise IntegrityError('Se modificó una transacción confirmada. Revisar respaldos.')
        return payload

    def _changes(self, manifest):
        if 'changes' in manifest:
            return manifest['changes']
        result = []
        for ref in manifest['chunks']:
            chunk = self._manifest(self.item('_commits', ref['item']))
            if digest(chunk) != ref['hash'] or chunk['transaction'] != manifest['tx']:
                raise IntegrityError('Fragmento de transacción inválido.')
            result.extend(chunk['changes'])
        return result

    def _load(self, control):
        head = control['fields'].get('Head', '')
        if self.cache and self.cache['head'] == head:
            return copy.deepcopy(self.cache)
        data = {t: {} for t in TABLES}
        commits, changes = {}, {}
        # Cold starts paginate all lists; warm requests load only the new chain.
        cached_head = self.cache['head'] if self.cache else ''
        if self.cache:
            data = copy.deepcopy(self.cache['data'])
        else:
            commits = {r['id']: r for r in self.items('_commits')}
            for table in TABLES:
                changes[table] = {r['id']: r for r in self.items(table)}
        chain, seen = [], set()
        cursor = head
        while cursor and cursor != cached_head:
            if cursor in seen:
                raise IntegrityError('Cadena de transacciones circular.')
            seen.add(cursor)
            item = commits.get(cursor) or self.item('_commits', cursor)
            manifest = self._manifest(item)
            chain.append(manifest)
            cursor = manifest['parent']
        if cached_head and cursor != cached_head:
            self.cache = None
            return self._load(control)
        for manifest in reversed(chain):
            for change in self._changes(manifest):
                table = change['table']
                if table not in TABLES:
                    raise IntegrityError('Tabla no reconocida.')
                item = changes.get(table, {}).get(change['item']) or self.item(table, change['item'])
                f = item['fields']
                row = json.loads(f['Payload'])
                if (f['TxId'] != manifest['tx'] or f['RowKey'] != change['key']
                        or digest(row) != change['hash']):
                    raise IntegrityError('Un registro confirmado no coincide con su respaldo de transacción.')
                if row is None:
                    data[table].pop(change['key'], None)
                else:
                    if row_key(table, row) != change['key']:
                        raise IntegrityError('Identificador de registro inválido.')
                    data[table][change['key']] = row
        if chain:
            sequences = chain[0]['sequences']
        else:
            sequences = self.cache['sequences'] if self.cache else {}
        snapshot = {'head': head, 'data': data, 'sequences': sequences}
        self.cache = copy.deepcopy(snapshot)
        return snapshot

    def snapshot(self):
        with self.lock:
            control = self.control()
            snap = self._load(control)
            snap['control'] = control
            return snap

    def contains_commit(self, commit_id):
        cursor = self.control()['fields'].get('Head', '')
        seen = set()
        while cursor:
            if cursor == commit_id:
                return True
            if cursor in seen:
                raise IntegrityError('Cadena circular.')
            seen.add(cursor)
            cursor = self._manifest(self.item('_commits', cursor))['parent']
        return False

    def commit(self, before, after, sequences):
        tx = uuid.uuid4().hex
        pending = []
        for table in TABLES:
            old, new = before['data'][table], after[table]
            for key in sorted(old.keys() | new.keys()):
                if old.get(key) != new.get(key):
                    row = new.get(key)
                    payload = canonical(row)
                    if len(payload) > 50000:
                        raise ValueError('Registro demasiado grande para SharePoint.')
                    pending.append((table, key, row, payload))
        if not pending:
            return
        if self.control()['eTag'] != before['control']['eTag']:
            raise Conflict()
        references = []
        for table, key, row, payload in pending:
            fields = {'Title': key, 'Key': tx + ':' + key, 'TxId': tx,
                      'RowKey': key, 'Payload': payload, 'Deleted': row is None}
            # Readable context without duplicating password hashes in preview columns.
            if row:
                fields['Summary'] = str(row.get('name', row.get('description', row.get('action', key))))[:250]
            item = self.create_unique(table, fields)
            references.append({'table': table, 'key': key, 'item': item['id'], 'hash': digest(row)})
        manifest = {'tx': tx, 'parent': before['head'], 'changes': references, 'sequences': sequences}
        payload = canonical(manifest)
        if len(payload) > 50000:
            chunks = []
            for offset in range(0, len(references), 150):
                chunk = {'tx': tx + ':' + str(offset), 'transaction': tx,
                         'changes': references[offset:offset + 150]}
                saved_chunk = self.create_unique('_commits', {'Title': chunk['tx'], 'Key': chunk['tx'],
                    'Payload': canonical(chunk), 'Digest': digest(chunk)})
                chunks.append({'item': saved_chunk['id'], 'hash': digest(chunk)})
            manifest.pop('changes')
            manifest['chunks'] = chunks
            payload = canonical(manifest)
            if len(payload) > 50000:
                raise ValueError('Importación demasiado grande; no se confirmó ningún cambio.')
        saved = self.create_unique('_commits', {'Title': tx, 'Key': tx, 'Payload': payload, 'Digest': digest(manifest)})
        commit_id = saved['id']
        control = before['control']
        try:
            self.graph.request('PATCH', self.path('_control') + '/' + control['id'] + '/fields',
                               {'Head': commit_id}, {'If-Match': control['eTag']})
        except GraphError as exc:
            if self.contains_commit(commit_id):
                return  # The write succeeded but its response was lost.
            if exc.status == 412:
                raise Conflict() from None
            raise RuntimeError('No se pudo confirmar la operación. Actualiza para verificar su estado antes de repetirla.') from None
        with self.lock:
            self.cache = {'head': commit_id, 'data': copy.deepcopy(after), 'sequences': dict(sequences)}


def text_column(name, multiline=False, unique=False):
    col = {'name': name, 'text': {'allowMultipleLines': multiline, 'textType': 'plain'}}
    if unique:
        col.update(indexed=True, enforceUniqueValues=True)
    return col


def provision(store):
    """Create missing dedicated lists only; never replace or delete existing ones."""
    root = f'/sites/{store.site}/lists'
    found = {r['displayName']: r for r in store.graph.pages(root + '?$select=id,displayName')}
    ids = {}
    for table, name in store.list_names().items():
        columns = [text_column('Key', unique=True)]
        if table == '_control':
            columns += [text_column('Head'), text_column('SchemaVersion')]
        elif table == '_commits':
            columns += [text_column('Payload', True), text_column('Digest')]
        else:
            columns += [dict(text_column('TxId'), indexed=True), text_column('RowKey'),
                        text_column('Payload', True), {'name': 'Deleted', 'boolean': {}}, text_column('Summary')]
        if name not in found:
            found[name] = store.graph.request('POST', root, {'displayName': name,
                'description': 'ALTIVIA HH CONTROL · registros versionados, editar solo mediante la aplicación.',
                'list': {'template': 'genericList'}, 'columns': columns})
        list_id = found[name]['id']
        actual = {r['name']: r for r in store.graph.pages(root + '/' + list_id + '/columns')}
        for expected in columns:
            col = actual.get(expected['name'])
            if col is None or ('text' in expected and 'text' not in col) or ('boolean' in expected and 'boolean' not in col):
                raise IntegrityError(f'Lista existente incompatible: {name}/{expected["name"]}. No se modificó.')
            if expected.get('enforceUniqueValues') and not col.get('enforceUniqueValues'):
                raise IntegrityError(f'La lista {name} no tiene la restricción única requerida.')
        ids[table] = list_id
    store.lists = ids
    if not store.unique('_control', 'root'):
        store.create_unique('_control', {'Title': 'ALTIVIA HH CONTROL', 'Key': 'root', 'SchemaVersion': '1', 'Head': ''})
    return ids
