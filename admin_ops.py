"""Administrative mutations, validated inside the storage transaction."""
import re
import unicodedata
from sqlalchemy import text
from werkzeug.security import generate_password_hash
from db import log


def account_word(value):
    value=''.join(ch for ch in unicodedata.normalize('NFKD',str(value).casefold()) if not unicodedata.combining(ch))
    return ''.join(re.findall('[a-z0-9]+',value))


def name_parts(fullname):
    """Suggestion only: administrators review/edit Excel name parts before import."""
    words=str(fullname).strip().split()
    if len(words)<2:return dict(Nombres=' '.join(words),Primer_apellido='',Otros_apellidos='')
    surname_index=len(words)-2 if len(words)>=3 else 1
    return dict(Nombres=' '.join(words[:surname_index]),Primer_apellido=words[surname_index],Otros_apellidos=' '.join(words[surname_index+1:]))


def require_admin(c,actor):
    user=c.execute(text('SELECT role,active FROM users WHERE id=:id AND deleted=0'),{'id':actor}).mappings().first()
    if not user or user['role']!='admin' or not user['active']:raise ValueError('Solo un administrador activo puede realizar esta operación.')


def create_collaborator(c,actor,names,first_surname,other_surnames='',role='trabajador'):
    require_admin(c,actor)
    names=' '.join(names.split()) if isinstance(names,str) else ''
    first_surname=' '.join(first_surname.split()) if isinstance(first_surname,str) else ''
    other_surnames=' '.join(other_surnames.split()) if isinstance(other_surnames,str) else ''
    if not names or not first_surname:raise ValueError('Completa los nombres y el primer apellido.')
    if role not in ('admin','supervisor','trabajador'):raise ValueError('Rol inválido.')
    root=account_word(names.split()[0]);password=account_word(first_surname)
    if not root or not password:raise ValueError('El nombre y apellido deben contener letras o números.')
    username=root;seq=2
    while c.execute(text('SELECT id FROM users WHERE username=:username'),{'username':username}).first():
        username=f'{root}{seq}';seq+=1
    fullname=' '.join(x for x in (names,first_surname,other_surnames) if x)
    uid=c.execute(text('INSERT INTO users(username,name,pw,role,must_change_pw) VALUES(:username,:name,:pw,:role,1) RETURNING id'),dict(username=username,name=fullname,pw=generate_password_hash(password),role=role)).scalar_one()
    log(c,actor,'crear_usuario','user',uid,'Usuario '+username)
    return dict(id=uid,name=fullname,username=username,initial_password=password)


def reset_password(c,actor,user_id,password):
    require_admin(c,actor)
    if user_id==actor:raise ValueError('Selecciona otro colaborador para restablecer su acceso.')
    if len(password)<6:raise ValueError('La contraseña temporal debe tener al menos 6 caracteres.')
    if not c.execute(text('SELECT id FROM users WHERE id=:id AND deleted=0'),{'id':user_id}).first():raise ValueError('El colaborador ya no está disponible.')
    c.execute(text('UPDATE users SET pw=:pw,must_change_pw=1 WHERE id=:id'),dict(pw=generate_password_hash(password),id=user_id))
    log(c,actor,'restablecer_contrasena','user',user_id,'Cambio obligatorio al ingresar')


def replace_assignments(c,actor,user_id,project_id,selected_ids,expected_ids,project_access=True,expected_access=None):
    require_admin(c,actor)
    if not c.execute(text('SELECT id FROM users WHERE id=:id AND deleted=0'),{'id':user_id}).first():raise ValueError('Colaborador no disponible.')
    if not c.execute(text('SELECT id FROM projects WHERE id=:id AND deleted=0'),{'id':project_id}).first():raise ValueError('Proyecto no disponible.')
    available={r['id'] for r in c.execute(text('SELECT id FROM activities WHERE project_id=:pid'),{'pid':project_id}).mappings().all()}
    current={r['activity_id'] for r in c.execute(text('SELECT aa.activity_id FROM activity_assignments aa JOIN activities a ON a.id=aa.activity_id WHERE aa.user_id=:uid AND a.project_id=:pid'),dict(uid=user_id,pid=project_id)).mappings().all()}
    selected=set(selected_ids)
    if current!=set(expected_ids):raise ValueError('Las asignaciones cambiaron. Actualiza la pantalla antes de guardar.')
    present=bool(c.execute(text('SELECT COUNT(*) FROM assignments WHERE user_id=:uid AND project_id=:pid'),dict(uid=user_id,pid=project_id)).scalar())
    if expected_access is not None and present!=expected_access:raise ValueError('El acceso al proyecto cambió. Actualiza la pantalla antes de guardar.')
    if not selected<=available:raise ValueError('Una actividad no pertenece al proyecto seleccionado.')
    if not project_access and selected:raise ValueError('Un proyecto sin acceso no puede conservar actividades autorizadas.')
    # Retained assignments keep their original planned hours; records/history are untouched.
    for aid in current-selected:c.execute(text('DELETE FROM activity_assignments WHERE user_id=:uid AND activity_id=:aid'),dict(uid=user_id,aid=aid))
    for aid in selected-current:c.execute(text('INSERT INTO activity_assignments(user_id,activity_id) VALUES(:uid,:aid) ON CONFLICT DO NOTHING'),dict(uid=user_id,aid=aid))
    if project_access:c.execute(text('INSERT INTO assignments(user_id,project_id) VALUES(:uid,:pid) ON CONFLICT DO NOTHING'),dict(uid=user_id,pid=project_id))
    else:c.execute(text('DELETE FROM assignments WHERE user_id=:uid AND project_id=:pid'),dict(uid=user_id,pid=project_id))
    log(c,actor,'editar_asignaciones','user',user_id,f'Proyecto {project_id}; agregadas {len(selected-current)}; retiradas {len(current-selected)}; acceso {project_access}')


def set_project_status(c,actor,project_id,status,expected_status):
    require_admin(c,actor)
    if status not in ('activo','desactivado','terminado'):raise ValueError('Estado inválido.')
    result=c.execute(text('UPDATE projects SET status=:status WHERE id=:id AND status=:expected AND deleted=0'),dict(status=status,id=project_id,expected=expected_status))
    if result.rowcount!=1:raise ValueError('El proyecto cambió. Actualiza la pantalla antes de continuar.')
    log(c,actor,'estado_proyecto','project',project_id,status)


def delete_user(c,actor,user_id):
    require_admin(c,actor)
    if user_id==actor:raise ValueError('No puedes eliminar tu propia cuenta.')
    user=c.execute(text('SELECT role,active FROM users WHERE id=:id AND deleted=0'),{'id':user_id}).mappings().first()
    if not user:raise ValueError('El usuario ya fue eliminado o no existe.')
    if user['role']=='admin' and user['active']:
        count=c.execute(text("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND deleted=0")).scalar()
        if count<=1:raise ValueError('Debe conservarse al menos un administrador activo.')
    c.execute(text('UPDATE users SET deleted=1,active=0 WHERE id=:id'),{'id':user_id})
    log(c,actor,'eliminar_usuario','user',user_id,'Eliminación recuperable; historial conservado')


def delete_project(c,actor,project_id):
    require_admin(c,actor)
    result=c.execute(text("UPDATE projects SET deleted=1,status='desactivado' WHERE id=:id AND deleted=0"),{'id':project_id})
    if result.rowcount!=1:raise ValueError('El proyecto ya fue eliminado o no existe.')
    log(c,actor,'eliminar_proyecto','project',project_id,'Eliminación recuperable; historial conservado')


def restore_user(c,actor,user_id):
    require_admin(c,actor)
    result=c.execute(text('UPDATE users SET deleted=0,active=0 WHERE id=:id AND deleted=1'),{'id':user_id})
    if result.rowcount!=1:raise ValueError('El usuario ya fue restaurado o no existe.')
    log(c,actor,'restaurar_usuario','user',user_id,'Restaurado inactivo; activar desde Usuarios y accesos')


def restore_project(c,actor,project_id):
    require_admin(c,actor)
    result=c.execute(text("UPDATE projects SET deleted=0,status='desactivado' WHERE id=:id AND deleted=1"),{'id':project_id})
    if result.rowcount!=1:raise ValueError('El proyecto ya fue restaurado o no existe.')
    log(c,actor,'restaurar_proyecto','project',project_id,'Restaurado desactivado')
