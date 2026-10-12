"""Checks that do not require installing Streamlit or accessing a database."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for file in [root/'app.py',root/'db.py',root/'tools/migrate_v7_sqlite.py']:
    ast.parse(file.read_text(encoding='utf-8'))
for needed in ['app.py','db.py','requirements.txt','.streamlit/config.toml','.streamlit/secrets.toml.example','tools/migrate_v7_sqlite.py']:
    assert (root/needed).is_file(),needed
source=(root/'app.py').read_text(encoding='utf8')
assert 'serve(app' not in source
assert 'st.set_page_config' in source
assert 'state=\'liquidado\'' in source
assert 'approval_at::date<=:cutoff' in source
assert 'st.data_editor' in source
assert "p.status='activo'" in source
print('OK: sources parsed and Streamlit-native structure present')
