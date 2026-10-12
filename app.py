"""ALTIVIA HH CONTROL — Streamlit native, SharePoint Lists edition.
Run: streamlit run app.py
"""
import io, re, secrets, unicodedata, hashlib, hmac
from datetime import date, datetime
from decimal import Decimal
import pandas as pd
import streamlit as st
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import load_workbook
from db import engine, init_schema, one, all_rows, scalar, exec_sql, log, reset_context
from sharepoint_graph import setting
from access import pages_for_role
from ui import apply_theme, brand, page_header, login_intro, section_note, project_card, shortcut, NAV_ICONS, sidebar_identity, empty_state

st.set_page_config(page_title='ALTIVIA · HH Control',page_icon=str(__import__('pathlib').Path(__file__).parent/'assets'/'altivia-logo.png'),layout='wide',initial_sidebar_state='expanded')
apply_theme()
reset_context()
try:init_schema()
except Exception as exc:
    st.error('No se pudo abrir el almacenamiento de ALTIVIA. Revisa la configuración privada y los permisos de conexión.');st.stop()

def norm(v):return ''.join(ch for ch in unicodedata.normalize('NFKD',str(v).casefold()) if not unicodedata.combining(ch)).strip()
def login_from_name(name):
    words=re.findall('[a-z0-9]+',norm(name));return words[-1] if words else 'trabajador'
def hours_to_quarters(v):
    d=Decimal(str(v))
    if d<=0 or d>12 or d*4 != (d*4).to_integral_value():raise ValueError('Ingrese entre 0.25 y 12 HH en incrementos de 0.25.')
    return int(d*4)
def money(v):return f'S/ {v/100:,.2f}'
def me():
    uid=st.session_state.get('uid')
    return one('SELECT * FROM users WHERE id=:i AND active=1',{'i':uid}) if uid else None

def require(role):
    if me()['role'] not in role:st.error('Acceso no autorizado.');st.stop()
def options(rows,key='name'):return {f"{r.get('code',r['id'])} · {r[key]}":r['id'] for r in rows}
def choose(title,rows,key='name',empty=False,k=None,selected_id=None,empty_label='Todos'):
    opts=options(rows,key);names=([empty_label] if empty else [])+list(opts)
    initial=next((label for label,ident in opts.items() if ident==selected_id),names[0] if names else None)
    selected=st.selectbox(title,names,key=k,index=names.index(initial)) if names else None
    return opts.get(selected)
def audit_event(c,action,target,tid=None,detail=''):log(c,me()['id'],action,target,tid,detail)

def authenticate():
    if scalar('SELECT COUNT(*) FROM users')==0:
        st.title('Configuración inicial · ALTIVIA')
        setup_token=setting('ALTIVIA_SETUP_TOKEN')
        if not setup_token:
            st.info('La inicialización está cerrada. El responsable debe habilitar la clave de instalación en la configuración privada.');st.stop()
        st.warning('Este formulario crea el primer administrador y requiere la clave privada de instalación.')
        with st.form('setup'):
            supplied_token=st.text_input('Clave de instalación',type='password')
            name=st.text_input('Nombre completo');login=st.text_input('Usuario administrador').lower().strip();pwd=st.text_input('Contraseña (mínimo 6 caracteres)',type='password');confirm=st.text_input('Repetir contraseña',type='password')
            submit=st.form_submit_button('Crear administrador')
        if submit:
            if not hmac.compare_digest(supplied_token,setup_token):st.error('Clave de instalación incorrecta.')
            elif not name.strip() or not re.fullmatch('[a-z0-9_.-]{3,40}',login) or len(pwd)<6 or pwd!=confirm:st.error('Verifica el nombre, usuario y contraseña (mínimo 6 caracteres).')
            else:
                with engine().begin() as c:
                    if c.execute(text('SELECT COUNT(*) FROM users')).scalar():
                        st.error('El administrador ya fue creado. Actualiza la página.');st.stop()
                    c.execute(text("INSERT INTO users(username,name,pw,role) VALUES(:l,:n,:pw,'admin')"),dict(l=login,n=name.strip(),pw=generate_password_hash(pwd)))
                st.success('Administrador creado; inicia sesión.');st.rerun()
        st.stop()
    if not me():
        left, spacer, right = st.columns([1.15,.12,1])
        with left:login_intro()
        with right:
            st.markdown('<div class="login-spacer"></div>',unsafe_allow_html=True)
            st.subheader('Bienvenido a ALTIVIA')
            st.caption('Ingresa con el usuario que te asignó el administrador.')
            with st.form('login'):
                login=st.text_input('Usuario',placeholder='Tu usuario de acceso').strip().lower()
                pwd=st.text_input('Contraseña',type='password',placeholder='Ingresa tu contraseña')
                submitted=st.form_submit_button('Ingresar',type='primary',use_container_width=True)
            st.caption('Acceso privado · Si necesitas ayuda, contacta al administrador de tu equipo.')
        if submitted:
            u=one('SELECT * FROM users WHERE username=:u AND active=1',{'u':login})
            if u and check_password_hash(u['pw'],pwd):
                st.session_state['uid']=u['id'];st.rerun()
            else:st.error('Usuario o contraseña incorrectos.')
        st.stop()
    if me()['must_change_pw']:
        st.title('Cambiar contraseña temporal')
        with st.form('change-pwd'):
            pwd=st.text_input('Nueva contraseña (mínimo 6 caracteres)',type='password');again=st.text_input('Repetir nueva contraseña',type='password');ok=st.form_submit_button('Actualizar contraseña')
        if ok:
            if len(pwd)<6 or pwd!=again:st.error('Usa una contraseña de al menos 6 caracteres, idéntica en los dos campos.')
            else:
                with engine().begin() as c:
                    c.execute(text('UPDATE users SET pw=:p,must_change_pw=0 WHERE id=:i'),dict(p=generate_password_hash(pwd),i=me()['id']))
                    audit_event(c,'cambio_contrasena','user',me()['id'])
                st.rerun()
        st.stop()

authenticate()
u=me()
brand(sidebar=True)
sidebar_identity(u)
st.sidebar.caption('ESPACIO DE TRABAJO')
menus=pages_for_role(u['role'])
if not menus:st.error('Acceso no autorizado.');st.stop()
# Validate on the server, including sessions whose role or navigation has changed.
if st.session_state.get('navigation') not in menus:st.session_state['navigation']=menus[0]
page=st.sidebar.radio('Navegación',menus,key='navigation',format_func=lambda x:f'{NAV_ICONS[x]}  {x}')
if page not in pages_for_role(u['role']):st.error('Acceso no autorizado.');st.stop()
st.sidebar.divider()
if st.sidebar.button('Cerrar sesión'):
    st.session_state.clear();st.rerun()
page_header(page,u)

def projects_access(include_inactive=True):
    if u['role']=='admin':cond='1=1';args={}
    elif u['role']=='supervisor':cond='supervisor_id=:uid';args={'uid':u['id']}
    else:cond='id IN (SELECT project_id FROM assignments WHERE user_id=:uid)';args={'uid':u['id']}
    if not include_inactive:cond+=" AND status='activo'"
    return all_rows('SELECT * FROM projects WHERE '+cond+' ORDER BY code',args)

def entries_query(pid=None,start=None,end=None,worker=None):
    clauses=[];args={}
    if u['role']=='trabajador':clauses.append('e.user_id=:viewer');args['viewer']=u['id']
    elif u['role']=='supervisor':clauses.append('p.supervisor_id=:viewer');args['viewer']=u['id']
    if pid:clauses.append('p.id=:pid');args['pid']=pid
    if start:clauses.append('e.work_date>=:start');args['start']=start
    if end:clauses.append('e.work_date<=:end');args['end']=end
    if worker:clauses.append('e.user_id=:worker');args['worker']=worker
    return all_rows('''SELECT e.*,us.name worker,p.code project,p.id project_id,a.code activity_code,a.name activity
        FROM entries e JOIN users us ON us.id=e.user_id JOIN activities a ON a.id=e.activity_id
        JOIN projects p ON p.id=a.project_id WHERE '''+(' AND '.join(clauses) if clauses else '1=1')+' ORDER BY e.work_date DESC,e.id DESC',args)

def date_filters():
    c1,c2,c3=st.columns([2,1,1]);projs=projects_access()
    with c1:pid=choose('Proyecto (opcional)',projs,empty=True)
    with c2:since=st.date_input('Desde',value=None,key='from_date')
    with c3:until=st.date_input('Hasta',value=None,key='to_date')
    if since and until and since>until:st.error('La fecha inicial supera la final.');st.stop()
    return pid,since,until

def render_personal_history():
    history=entries_query(worker=u['id'])[:250]
    if not history:
        empty_state('Todavía no registras horas','Crea tu primer registro desde Registrar horas.','◷')
        return
    states={'pendiente':'Pendiente','aprobado':'Aprobado','liquidado':'Aprobado','observado':'Observado','rechazado':'Rechazado'}
    c1,c2,c3=st.columns(3)
    c1.metric('Mis horas registradas',f"{sum(r['quarters'] for r in history)/4:,.2f} HH")
    c2.metric('Pendientes de revisión',f"{sum(r['quarters'] for r in history if r['state']=='pendiente')/4:,.2f} HH")
    c3.metric('Aprobadas',f"{sum(r['quarters'] for r in history if r['state'] in ('aprobado','liquidado'))/4:,.2f} HH")
    st.caption('Resumen de tus últimos 250 registros. Los filtros siguientes se aplican al detalle.')
    c1,c2=st.columns(2)
    with c1:selected_project=st.selectbox('Filtrar mi proyecto',['Todos']+sorted({r['project'] for r in history}),key='personal_project')
    with c2:selected_state=st.selectbox('Estado de mis horas',['Todos','Pendiente','Aprobado','Observado','Rechazado'],key='personal_state')
    filtered=[r for r in history if (selected_project=='Todos' or r['project']==selected_project) and (selected_state=='Todos' or states[r['state']]==selected_state)]
    if filtered:
        st.dataframe(pd.DataFrame([dict(ID=r['id'],Fecha=r['work_date'],Proyecto=r['project'],EDT=r['activity_code'],Actividad=r['activity'],HH=r['quarters']/4,Estado=states[r['state']],Descripción=r['description'],Observación=r['note']) for r in filtered]),hide_index=True,use_container_width=True,column_config={'HH':st.column_config.NumberColumn('Horas registradas',format='%.2f')})
    else:st.info('No hay registros que coincidan con estos filtros.')
    observed=[r for r in history if r['state']=='observado']
    if observed:
        st.subheader('Corregir registros observados')
        eid=st.selectbox('Registro observado', [r['id'] for r in observed],format_func=lambda i:f"#{i} · {next(x['activity'] for x in observed if x['id']==i)}")
        r=next(x for x in observed if x['id']==eid)
        with st.form('fix'):
            h=st.number_input('HH corregidas',value=r['quarters']/4,min_value=.25,max_value=12.,step=.25)
            desc=st.text_area('Descripción corregida',value=r['description'])
            if st.form_submit_button('Reenviar'):
                with engine().begin() as c:
                    result=c.execute(text('''UPDATE entries SET quarters=:q,description=:d,state='pendiente',note='',approval_by=NULL,approval_at=NULL,updated_at=NOW()
                        WHERE id=:id AND user_id=:uid AND state='observado' AND EXISTS (SELECT 1 FROM activities a JOIN projects p ON p.id=a.project_id WHERE a.id=entries.activity_id AND p.status='activo' AND a.active=1)'''),dict(q=hours_to_quarters(h),d=desc,id=eid,uid=u['id']))
                    if result.rowcount!=1:raise ValueError('Registro no disponible para corrección.')
                    audit_event(c,'corregir_hh','entry',eid)
                st.rerun()


if page=='Centro gerencial':
    require(('admin','supervisor'))
    with st.container(border=True,key='dashboard_filters'):
        st.caption('ALCANCE DEL REPORTE')
        pid,start,end=date_filters()
    projs=[p for p in projects_access() if not pid or p['id']==pid]
    entries=[r for r in entries_query(pid,start,end) if r['state'] in ('pendiente','aprobado','liquidado')]
    budgets={r['project_id']:r['qty'] for r in all_rows('SELECT project_id,COALESCE(SUM(budget_quarters),0) qty FROM activities GROUP BY project_id')}
    budget=sum(budgets.get(p['id'],0) for p in projs)/4
    total=sum(e['quarters'] for e in entries)/4
    approved=sum(e['quarters'] for e in entries if e['state'] in ('aprobado','liquidado'))/4
    pending=sum(e['quarters'] for e in entries if e['state']=='pendiente')/4
    k=st.columns(4)
    for col,label,val in zip(k,['Presupuesto total','HH registradas','HH aprobadas','HH por aprobar'],[budget,total,approved,pending]):
        col.metric(label,f'{val:,.2f} HH',help='Horas hombre (HH). El presupuesto corresponde al total de las actividades; las horas siguen los filtros seleccionados.')
    st.caption('Valores en HH · Presupuesto total de actividades. Consumo y pendientes según los filtros seleccionados.')
    st.markdown('')
    main, side=st.columns([2.1,1],gap='large')
    with main:
        st.subheader('Estado de los proyectos')
        st.caption('Compara el presupuesto con las horas del alcance seleccionado.')
        rows=[]
        if not projs:
            st.info('Aún no hay proyectos disponibles en este alcance.')
            if u['role']=='admin':shortcut('Crear el primer proyecto','Proyectos y actividades','first_project')
        for p in projs:
            e=[x for x in entries if x['project_id']==p['id']]
            q=sum(x['quarters'] for x in e)/4;b=budgets.get(p['id'],0)/4
            ap=sum(x['quarters'] for x in e if x['state'] in ('aprobado','liquidado'))/4
            pe=sum(x['quarters'] for x in e if x['state']=='pendiente')/4
            project_card(p,b,q,ap,pe)
            rows.append(dict(Proyecto=f"{p['code']} · {p['name']}",Estado=p['status'],Presupuesto_HH=b,HH_cargadas=q,HH_aprobadas=ap,HH_por_aprobar=pe,Diferencia_HH=b-q,Consumo_pct=round(q/b*100,1) if b else 0))
    with side:
        st.subheader('Tu siguiente acción')
        with st.container(border=True,key='priority_review'):
            reviewable=[e for e in entries_query() if e['state']=='pendiente' and e['user_id']!=u['id']]
            if u['role'] in ('admin','supervisor'):
                st.markdown(f"**{len(reviewable)} registros por revisar**")
                st.caption('La bandeja de aprobación reúne todos los registros pendientes de tu alcance, sin el filtro de fechas de este reporte.')
                shortcut('Ir a aprobaciones →','Aprobaciones','quick_review')
            else:
                st.markdown('**Mantén tus horas al día**')
                st.caption('Registra la actividad realizada y envíala para revisión.')
                shortcut('Registrar mis horas →','Mis HH','quick_hours')
        if u['role']=='admin':
            assigned=all_rows('SELECT DISTINCT u.id,u.name,r.rate_cents FROM users u JOIN assignments a ON a.user_id=u.id LEFT JOIN rates r ON r.user_id=u.id WHERE u.active=1')
            missing=[x for x in assigned if x['rate_cents'] is None]
            with st.container(border=True,key='priority_close'):
                st.markdown('**Preparación del cierre**')
                st.caption(f"{len(missing)} profesionales asignados sin tarifa. Configura sus tarifas antes de liquidar." if missing else 'Consulta las horas aprobadas, elige el corte y revisa los importes antes de cerrar.')
                shortcut('Configurar tarifas →' if missing else 'Ver liquidaciones →','Usuarios y tarifas' if missing else 'Liquidaciones','quick_close')
        with st.container(border=True,key='priority_budget'):
            st.markdown('**Control del presupuesto**')
            st.caption('Revisa la dedicación de cada actividad y detecta desviaciones a tiempo.')
            if u['role'] in ('admin','supervisor'):shortcut('Ver presupuesto EDT →','Presupuestos EDT','quick_budget')
            else:shortcut('Consultar mis horas →','Mis HH','quick_history')
    with st.expander('Comparativo detallado y descarga'):
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,column_config={'Consumo_pct':st.column_config.ProgressColumn('Consumo (%)',min_value=0,max_value=max(100,max((x['Consumo_pct'] for x in rows),default=100)),format='%.1f%%'),'Presupuesto_HH':st.column_config.NumberColumn('Presupuesto (HH)',format='%.2f'),'HH_cargadas':st.column_config.NumberColumn('Registradas (HH)',format='%.2f'),'Diferencia_HH':st.column_config.NumberColumn('Saldo (HH)',format='%.2f')})
        if rows:
            st.bar_chart(pd.DataFrame(rows).set_index('Proyecto')[['Presupuesto_HH','HH_cargadas']],color=['#13364a','#077e78'],stack=False)
    if u['role']=='admin':
        with st.expander('Guía del administrador · configura tu equipo en orden'):
            c1,c2,c3=st.columns(3)
            with c1:
                st.markdown('**01 · Organiza el trabajo**')
                st.caption('Crea el proyecto y su responsable. Añade actividades o importa tu matriz Excel.')
                shortcut('Proyectos y actividades','Proyectos y actividades','guide_projects')
                shortcut('Importar matriz Excel','Importar Excel','guide_import')
            with c2:
                st.markdown('**02 · Prepara al equipo**')
                st.caption('Crea usuarios, revisa sus tarifas y asigna las actividades que pueden registrar.')
                shortcut('Usuarios, tarifas y asignaciones','Usuarios y tarifas','guide_team')
            with c3:
                st.markdown('**03 · Revisa y cierra**')
                st.caption('Aprueba el trabajo, controla el presupuesto y liquida las horas aprobadas por fecha de corte.')
                shortcut('Bandeja de aprobaciones','Aprobaciones','guide_review')

elif page in ('Mis HH','Registrar horas'):
    section_note('Registro diario','Selecciona proyecto y actividad, indica las horas y describe el trabajo realizado. Máximo 12 HH por día.')
    projs=projects_access(False)
    if not projs:empty_state('No tienes proyectos activos asignados','Solicita al administrador acceso a un proyecto y sus actividades.','▦')
    else:
        pid=choose('1. Selecciona el proyecto',projs)
        acts=all_rows('''SELECT a.id,a.code,a.name FROM activities a JOIN activity_assignments aa ON aa.activity_id=a.id
            WHERE aa.user_id=:uid AND a.project_id=:pid AND a.active=1 ORDER BY a.code''',dict(uid=u['id'],pid=pid)) if pid else []
        if not acts:empty_state('No tienes actividades autorizadas','Solicita al administrador la asignación de las actividades de este proyecto.','▦')
        else:
            with st.form('new-entry',clear_on_submit=True):
                activity_id=choose('2. Selecciona actividad',acts)
                c1,c2=st.columns(2)
                with c1:work_date=st.date_input('Fecha de trabajo',date.today())
                with c2:hh=st.number_input('Horas hombre',min_value=0.25,max_value=12.,step=.25,value=1.)
                description=st.text_area('Descripción técnica',max_chars=1500)
                sent=st.form_submit_button('Enviar para aprobación',type='primary')
            if sent:
                try:
                    q=hours_to_quarters(hh)
                    if not description.strip():raise ValueError('Describe el trabajo realizado.')
                    with engine().begin() as c:
                        valid=c.execute(text('''SELECT a.id FROM activities a JOIN projects p ON p.id=a.project_id JOIN activity_assignments aa ON aa.activity_id=a.id
                            WHERE a.id=:aid AND p.id=:pid AND p.status='activo' AND a.active=1 AND aa.user_id=:uid'''),dict(aid=activity_id,pid=pid,uid=u['id'])).first()
                        if not valid:raise ValueError('La actividad ya no está disponible para registrar HH.')
                        day_q=c.execute(text("SELECT COALESCE(SUM(quarters),0) FROM entries WHERE user_id=:u AND work_date=:d AND state NOT IN ('rechazado','observado')"),dict(u=u['id'],d=work_date)).scalar()
                        if day_q+q>48:raise ValueError('La jornada no puede superar 12 HH.')
                        eid=c.execute(text('''INSERT INTO entries(user_id,activity_id,work_date,quarters,description,state,submission_key)
                            VALUES(:uid,:aid,:dt,:q,:desc,'pendiente',:key) RETURNING id'''),dict(uid=u['id'],aid=activity_id,dt=work_date,q=q,desc=description.strip(),key=secrets.token_hex(16))).scalar_one()
                        audit_event(c,'registrar_hh','entry',eid)
                    st.success('HH registradas y enviadas para aprobación.');st.rerun()
                except Exception as exc:st.error(str(exc))
    if page=='Mis HH':
        st.subheader('Historial personal')
        render_personal_history()

elif page=='Mi historial':
    render_personal_history()

elif page=='HH por profesional':
    pid,start,end=date_filters();entries=entries_query(pid,start,end)
    rows={}
    for e in entries:
        if e['state'] not in ('pendiente','aprobado','liquidado'):continue
        key=(e['worker'],e['project']);r=rows.setdefault(key,dict(Profesional=e['worker'],Proyecto=e['project'],HH_cargadas=0,HH_aprobadas=0,HH_por_aprobar=0,HH_liquidadas=0))
        q=e['quarters']/4;r['HH_cargadas']+=q
        if e['state'] in ('aprobado','liquidado'):r['HH_aprobadas']+=q
        if e['state']=='pendiente':r['HH_por_aprobar']+=q
        if e['state']=='liquidado':r['HH_liquidadas']+=q
    st.dataframe(pd.DataFrame(list(rows.values())),hide_index=True,use_container_width=True)
    with st.expander('Ver detalle por actividad'):
        st.dataframe(pd.DataFrame([dict(Profesional=r['worker'],Proyecto=r['project'],EDT=r['activity_code'],Actividad=r['activity'],Fecha=r['work_date'],HH=r['quarters']/4,Estado=r['state']) for r in entries]),use_container_width=True,hide_index=True)

elif page=='Aprobaciones':
    pending=[r for r in entries_query() if r['state']=='pendiente' and r['user_id']!=u['id']]
    c1,c2=st.columns(2)
    c1.metric('Registros por revisar',len(pending));c2.metric('Horas por revisar',f"{sum(r['quarters'] for r in pending)/4:,.2f} HH")
    section_note('Revisa antes de decidir','Aprobar valida las horas. Observar permite que el profesional corrija. Rechazar descarta el registro con un motivo.')
    if not pending:empty_state('Bandeja al día','No hay horas pendientes que requieran tu aprobación.','✓')
    if pending:st.dataframe(pd.DataFrame([dict(ID=r['id'],Trabajador=r['worker'],Proyecto=r['project'],Actividad=r['activity'],Fecha=r['work_date'],HH=r['quarters']/4,Descripción=r['description']) for r in pending]),hide_index=True,use_container_width=True)
    if pending:
        with st.form('approve'):
            eid=st.selectbox('Registro', [r['id'] for r in pending],format_func=lambda i:next(f"#{r['id']} · {r['worker']} · {r['project']} · {r['quarters']/4:.2f} HH" for r in pending if r['id']==i))
            decision=st.radio('Decisión',['Aprobar','Observar','Rechazar'],horizontal=True)
            note=st.text_area('Observación / motivo')
            if st.form_submit_button('Registrar decisión'):
                if decision!='Aprobar' and not note.strip():st.error('Debes ingresar el motivo.')
                else:
                    state={'Aprobar':'aprobado','Observar':'observado','Rechazar':'rechazado'}[decision]
                    with engine().begin() as c:
                        rr=c.execute(text('''UPDATE entries e SET state=:s,note=:note,approval_by=:reviewer,approval_at=NOW(),updated_at=NOW()
                            FROM activities a JOIN projects p ON p.id=a.project_id WHERE e.id=:eid AND e.activity_id=a.id AND e.state='pendiente'
                            AND e.user_id<>:reviewer AND (:is_admin=1 OR p.supervisor_id=:reviewer)'''),dict(s=state,note=note,reviewer=u['id'],eid=eid,is_admin=int(u['role']=='admin')))
                        if rr.rowcount!=1:raise ValueError('No puedes aprobar este registro.')
                        audit_event(c,'revision_'+state,'entry',eid,note)
                    st.success('Revisión registrada.');st.rerun()

elif page=='Presupuestos EDT':
    section_note('Lectura del presupuesto','El consumo incluye horas pendientes, aprobadas y liquidadas. Un saldo negativo señala un exceso de presupuesto.')
    pid=choose('Proyecto',projects_access())
    rows=all_rows('''SELECT a.code,a.name,a.budget_quarters,COALESCE(SUM(CASE WHEN e.state IN ('pendiente','aprobado','liquidado') THEN e.quarters ELSE 0 END),0) consumed
      FROM activities a LEFT JOIN entries e ON e.activity_id=a.id WHERE a.project_id=:pid GROUP BY a.id ORDER BY a.code''',{'pid':pid}) if pid else []
    st.dataframe(pd.DataFrame([dict(EDT=r['code'],Actividad=r['name'],Presupuesto_HH=r['budget_quarters']/4,HH_cargadas=r['consumed']/4,Saldo_HH=(r['budget_quarters']-r['consumed'])/4) for r in rows]),hide_index=True,use_container_width=True)
elif page=='Proyectos y actividades':
    section_note('Organiza el proyecto','Primero crea el proyecto y asigna un supervisor. Después agrega sus actividades y revisa las horas presupuestadas.')
    with st.expander('Nuevo proyecto'):
        with st.form('newproj'):
            code=st.text_input('Código (único)');name=st.text_input('Nombre');supervisors=all_rows("SELECT id,name FROM users WHERE role IN ('supervisor','admin') AND active=1 ORDER BY name")
            sup=choose('Supervisor responsable',supervisors,empty=True,empty_label='Sin asignar');save=st.form_submit_button('Crear proyecto')
        if save:
            try:
                with engine().begin() as c:
                    iid=c.execute(text("INSERT INTO projects(code,name,supervisor_id) VALUES(:code,:name,:sup) RETURNING id"),dict(code=code.strip(),name=name.strip(),sup=sup)).scalar_one()
                    audit_event(c,'crear_proyecto','project',iid)
                st.rerun()
            except Exception as e:st.error(str(e))
    projs=projects_access();pid=choose('Selecciona proyecto',projs)
    if pid:
        p=next(x for x in projs if x['id']==pid)
        settings_tab,activities_tab=st.tabs(['Datos del proyecto','Actividades y presupuesto'])
        with settings_tab:
            with st.form('change-project'):
                code=st.text_input('Código',value=p['code']);name=st.text_input('Nombre',value=p['name']);status=st.selectbox('Estado',['activo','desactivado','terminado'],index=['activo','desactivado','terminado'].index(p['status']))
                sup=choose('Supervisor',all_rows("SELECT id,name FROM users WHERE role IN ('supervisor','admin') AND active=1"),empty=True,selected_id=p['supervisor_id'],empty_label='Sin asignar',k=f'supervisor_{pid}')
                if st.form_submit_button('Guardar proyecto'):
                    with engine().begin() as c:
                        c.execute(text('UPDATE projects SET code=:cd,name=:n,status=:s,supervisor_id=:sup WHERE id=:pid'),dict(cd=code.strip(),n=name.strip(),s=status,sup=sup,pid=pid))
                        audit_event(c,'editar_proyecto','project',pid,'Estado '+status)
                    st.rerun()
            st.info('Los proyectos desactivados o terminados bloquean la carga y corrección de HH, pero conservan el historial.')
        with activities_tab:
            acts=all_rows('SELECT id,code,name,budget_quarters,active FROM activities WHERE project_id=:pid ORDER BY code',{'pid':pid})
            st.subheader('Actividades · edición en tabla')
            if acts:
                df=pd.DataFrame([dict(ID=r['id'],EDT=r['code'],Actividad=r['name'],Presupuesto_HH=r['budget_quarters']/4,Activa=bool(r['active'])) for r in acts])
                edited=st.data_editor(df,hide_index=True,use_container_width=True,disabled=['ID'],num_rows='fixed',key='activities_edit')
                if st.button('Guardar modificaciones de actividades',type='primary'):
                    try:
                        with engine().begin() as c:
                            for _,r in edited.iterrows():
                                b=Decimal(str(r['Presupuesto_HH']))
                                if b<0 or b*4!=(b*4).to_integral_value():raise ValueError('El presupuesto debe ser múltiplo de 0.25 HH.')
                                c.execute(text('UPDATE activities SET code=:code,name=:name,budget_quarters=:q,active=:active WHERE id=:id AND project_id=:pid'),dict(code=str(r['EDT']).strip(),name=str(r['Actividad']).strip(),q=int(b*4),active=int(bool(r['Activa'])),id=int(r['ID']),pid=pid))
                            audit_event(c,'edicion_masiva_actividades','project',pid)
                        st.success('Actividades actualizadas.');st.rerun()
                    except Exception as exc:st.error(str(exc))
            with st.expander('Agregar actividad'):
                with st.form('newact'):
                    cd=st.text_input('EDT/WBS');nm=st.text_input('Actividad');budget=st.number_input('HH presupuesto',min_value=0.,step=.25)
                    if st.form_submit_button('Agregar'):
                        try:
                            with engine().begin() as c:
                                aid=c.execute(text('INSERT INTO activities(project_id,code,name,budget_quarters) VALUES(:pid,:code,:name,:b) RETURNING id'),dict(pid=pid,code=cd.strip(),name=nm.strip(),b=int(Decimal(str(budget))*4))).scalar_one()
                                audit_event(c,'crear_actividad','activity',aid)
                            st.rerun()
                        except Exception as exc:st.error(str(exc))

elif page=='Usuarios y tarifas':
    section_note('Configura el equipo','1. Crea usuarios y define sus roles. 2. Guarda sus tarifas. 3. Autoriza proyectos y actividades.')
    st.caption('Las tarifas no tienen fecha de vigencia. Los cierres anteriores conservan la tarifa congelada.')
    accounts_tab,rates_tab,assignments_tab=st.tabs(['Usuarios y accesos','Tarifas por hora','Asignaciones'])
    with accounts_tab:
        users=all_rows('SELECT id,username,name,role,active,must_change_pw FROM users ORDER BY name')
        df=pd.DataFrame([dict(ID=x['id'],Usuario=x['username'],Nombre=x['name'],Rol=x['role'],Activo=bool(x['active'])) for x in users])
        edited=st.data_editor(df,hide_index=True,use_container_width=True,disabled=['ID'],column_config={'Rol':st.column_config.SelectboxColumn(options=['admin','supervisor','trabajador'])},key='useredit')
        if st.button('Guardar cambios de usuarios',type='primary'):
            try:
                with engine().begin() as c:
                    active_admins=0
                    for _,row in edited.iterrows():
                        if row['Rol']=='admin' and row['Activo']:active_admins+=1
                    if active_admins<1:raise ValueError('Debe existir al menos un administrador activo.')
                    for _,row in edited.iterrows():
                        c.execute(text('UPDATE users SET username=:login,name=:name,role=:role,active=:active WHERE id=:id'),dict(login=str(row['Usuario']).lower().strip(),name=str(row['Nombre']).strip(),role=row['Rol'],active=int(row['Activo']),id=int(row['ID'])))
                    audit_event(c,'edicion_usuarios','users')
                st.success('Usuarios actualizados.');st.rerun()
            except Exception as exc:st.error(str(exc))
        with st.expander('Crear usuario manualmente'):
            with st.form('newusr'):
                name=st.text_input('Nombre completo');login=st.text_input('Usuario (opcional)');role=st.selectbox('Rol',['trabajador','supervisor','admin']);pwd=st.text_input('Contraseña temporal (mín. 6 caracteres)',type='password')
                if st.form_submit_button('Crear'):
                    if len(pwd)<6:st.error('La contraseña temporal debe tener al menos 6 caracteres.')
                    else:
                        try:
                            with engine().begin() as c:
                                uid=c.execute(text('INSERT INTO users(username,name,pw,role,must_change_pw) VALUES(:login,:name,:pw,:role,1) RETURNING id'),dict(login=(login.strip().lower() or login_from_name(name)),name=name.strip(),pw=generate_password_hash(pwd),role=role)).scalar_one()
                                audit_event(c,'crear_usuario','user',uid)
                            st.rerun()
                        except Exception as exc:st.error(str(exc))
    with rates_tab:
        st.subheader('Tarifas estándar por HH')
        rates=all_rows('SELECT u.id,u.name,r.rate_cents FROM users u LEFT JOIN rates r ON r.user_id=u.id WHERE u.active=1 ORDER BY u.name')
        rdf=pd.DataFrame([dict(ID=r['id'],Trabajador=r['name'],Tarifa_Soles=round((r['rate_cents'] or 0)/100,2)) for r in rates])
        edited_rates=st.data_editor(rdf,hide_index=True,use_container_width=True,disabled=['ID','Trabajador'],key='rates_edit')
        if st.button('Guardar tarifas',type='primary'):
            try:
                with engine().begin() as c:
                    for _,r in edited_rates.iterrows():
                        cents=int((Decimal(str(r['Tarifa_Soles']))*100).quantize(Decimal('1')))
                        if cents<0:raise ValueError('No se aceptan tarifas negativas.')
                        c.execute(text('INSERT INTO rates(user_id,rate_cents) VALUES(:u,:rate) ON CONFLICT (user_id) DO UPDATE SET rate_cents=EXCLUDED.rate_cents'),dict(u=int(r['ID']),rate=cents))
                    audit_event(c,'actualizar_tarifas','rates')
                st.success('Tarifas actualizadas.');st.rerun()
            except Exception as e:st.error(str(e))
    with assignments_tab:
        with st.container(border=True):
            st.subheader('Autorizar actividades')
            st.caption('El profesional podrá registrar horas únicamente en las actividades que selecciones. Las nuevas autorizaciones se agregan a las existentes.')
            people=all_rows('SELECT id,name FROM users WHERE active=1 ORDER BY name');person=choose('Trabajador',people)
            pid=choose('Proyecto',projects_access());aa=all_rows('SELECT id,code,name FROM activities WHERE project_id=:pid ORDER BY code',{'pid':pid}) if pid else []
            selected=st.multiselect('Actividades autorizadas',list(options(aa)),key='assign_act')
            if st.button('Agregar asignaciones'):
                with engine().begin() as c:
                    c.execute(text('INSERT INTO assignments(user_id,project_id) VALUES(:u,:p) ON CONFLICT DO NOTHING'),dict(u=person,p=pid))
                    for label in selected:c.execute(text('INSERT INTO activity_assignments(user_id,activity_id) VALUES(:u,:a) ON CONFLICT DO NOTHING'),dict(u=person,a=options(aa)[label]))
                    audit_event(c,'asignar_actividades','user',person)
                st.success('Asignaciones registradas.')

elif page=='Importar Excel':
    section_note('Antes de importar','Selecciona el proyecto destino. La vista previa te permitirá revisar actividades, profesionales y horas antes de guardar.')
    with st.expander('Formato requerido del archivo Excel'):
        st.write('Hoja **Estimado de Costos**: EDT en columna B; actividad en C; profesionales en fila 5, columnas J:T; horas positivas en cada cruce. Se admiten archivos .xlsx.')
    pid=choose('Proyecto destino',projects_access())
    file=st.file_uploader('Seleccionar libro .xlsx',type=['xlsx'])
    if file and pid:
        try:
            wb=load_workbook(io.BytesIO(file.getvalue()),read_only=True,data_only=True)
            if 'Estimado de Costos' not in wb.sheetnames:raise ValueError('No existe la hoja Estimado de Costos.')
            ws=wb['Estimado de Costos'];persons=[(col,str(ws.cell(5,col).value).strip()) for col in range(10,21) if ws.cell(5,col).value and norm(ws.cell(5,col).value) not in ('tbd','por definir')]
            preview=[]
            for row in ws.iter_rows(min_row=10,values_only=True):
                code=row[1] if len(row)>2 else None;title=row[2] if len(row)>2 else None
                if isinstance(code,bool) or not isinstance(code,(int,float)) or not title:continue
                code=str(int(code)) if float(code).is_integer() else str(code)
                if code.endswith('000'):continue
                cross=[]
                for col,fullname in persons:
                    val=row[col-1] if len(row)>=col else None
                    if isinstance(val,(int,float)) and not isinstance(val,bool) and val>0:
                        q=Decimal(str(val))*4
                        if q==q.to_integral_value():cross.append((fullname,int(q)))
                if cross:preview.append(dict(code=code,name=str(title).strip(),cross=cross,budget=sum(q for _,q in cross)))
            st.write(f'{len(persons)} profesionales identificados · {len(preview)} actividades asignables.')
            st.dataframe(pd.DataFrame([dict(EDT=x['code'],Actividad=x['name'],Presupuesto_HH=x['budget']/4,Profesionales=', '.join(n for n,_ in x['cross'])) for x in preview]),use_container_width=True,hide_index=True)
            st.warning('La importación sustituye asignaciones de las actividades incluidas. No sustituye la base completa. Verifica el proyecto.')
            if st.button('Confirmar importación de matriz',type='primary'):
                with engine().begin() as c:
                    mapping={}
                    for _,fullname in persons:
                        existing=c.execute(text('SELECT id FROM users WHERE lower(name)=lower(:name)'),{'name':fullname}).scalar()
                        if existing:mapping[fullname]=existing;continue
                        root=login_from_name(fullname);login=root;seq=2
                        while c.execute(text('SELECT 1 FROM users WHERE username=:login'),{'login':login}).first():login=f'{root}{seq}';seq+=1
                        # Random invitation password prevents predictable name-based credentials in public deployment.
                        initial=secrets.token_urlsafe(18)
                        uid=c.execute(text('INSERT INTO users(username,name,pw,role,must_change_pw) VALUES(:login,:name,:pw,\'trabajador\',1) RETURNING id'),dict(login=login,name=fullname,pw=generate_password_hash(initial))).scalar_one()
                        mapping[fullname]=uid
                        st.session_state.setdefault('new_import_credentials',[]).append((fullname,login,initial))
                    for item in preview:
                        existing=c.execute(text('SELECT id FROM activities WHERE project_id=:pid AND code=:code'),dict(pid=pid,code=item['code'])).scalar()
                        if existing:
                            aid=existing
                            if c.execute(text("SELECT 1 FROM entries WHERE activity_id=:a AND state='liquidado' LIMIT 1"),{'a':aid}).first():raise ValueError(f"No se puede reemplazar actividad {item['code']} con HH liquidadas.")
                            c.execute(text('UPDATE activities SET name=:name,budget_quarters=:b,active=1 WHERE id=:id'),dict(name=item['name'],b=item['budget'],id=aid))
                            c.execute(text('DELETE FROM activity_assignments WHERE activity_id=:aid'),{'aid':aid})
                        else:aid=c.execute(text('INSERT INTO activities(project_id,code,name,budget_quarters) VALUES(:pid,:code,:name,:b) RETURNING id'),dict(pid=pid,code=item['code'],name=item['name'],b=item['budget'])).scalar_one()
                        for fullname,quarters in item['cross']:
                            uid=mapping[fullname]
                            c.execute(text('INSERT INTO assignments(user_id,project_id) VALUES(:uid,:pid) ON CONFLICT DO NOTHING'),dict(uid=uid,pid=pid))
                            c.execute(text('INSERT INTO activity_assignments(user_id,activity_id,planned_quarters) VALUES(:uid,:aid,:q) ON CONFLICT (user_id,activity_id) DO UPDATE SET planned_quarters=EXCLUDED.planned_quarters'),dict(uid=uid,aid=aid,q=quarters))
                    c.execute(text('INSERT INTO import_log(project_id,filename,actor_id,notes) VALUES(:pid,:file,:actor,:notes)'),dict(pid=pid,file=file.name,actor=u['id'],notes=f'{len(preview)} actividades'))
                    audit_event(c,'importar_excel','project',pid)
                st.success('Importación completada.');st.rerun()
            credentials=st.session_state.get('new_import_credentials',[])
            if credentials:
                st.warning('Credenciales iniciales aleatorias, mostradas una sola vez. Entrega cada contraseña privadamente.')
                st.dataframe(pd.DataFrame(credentials,columns=['Nombre','Usuario','Contraseña temporal']),hide_index=True)
                if st.button('Ocultar credenciales'):st.session_state.pop('new_import_credentials',None);st.rerun()
        except Exception as e:st.error(str(e))

elif page=='Liquidaciones':
    section_note('Cierre del periodo','El corte considera la fecha de trabajo y de aprobación. Cada registro se liquida una sola vez; la tarifa queda congelada en el cierre.')
    cutoff=st.date_input('Fecha de corte',date.today());workers=all_rows("SELECT id,name FROM users WHERE role IN ('trabajador','supervisor','admin') AND active=1 ORDER BY name")
    candidates=all_rows('''SELECT us.id,us.name,COUNT(e.id) records,COALESCE(SUM(e.quarters),0) quarters,r.rate_cents
        FROM users us JOIN entries e ON e.user_id=us.id LEFT JOIN rates r ON r.user_id=us.id
        WHERE e.state='aprobado' AND e.liquidation_id IS NULL AND e.work_date<=:cutoff AND e.approval_at::date<=:cutoff
        GROUP BY us.id,r.rate_cents ORDER BY us.name''',{'cutoff':cutoff})
    st.subheader('HH listas para liquidar')
    st.dataframe(pd.DataFrame([dict(Trabajador=x['name'],Registros=x['records'],HH=x['quarters']/4,Tarifa=money(x['rate_cents']) if x['rate_cents'] is not None else 'SIN TARIFA',Importe=money(x['quarters']*x['rate_cents']//4) if x['rate_cents'] is not None else '-') for x in candidates]),hide_index=True,use_container_width=True)
    if candidates:
        uid=choose('Trabajador a liquidar',candidates)
        if st.button('Cerrar liquidación de este trabajador',type='primary'):
            try:
                with engine().begin() as c:
                    rate=c.execute(text('SELECT rate_cents FROM rates WHERE user_id=:uid'),{'uid':uid}).scalar()
                    if rate is None:raise ValueError('Debes configurar la tarifa del trabajador.')
                    records=c.execute(text('''SELECT id,quarters FROM entries WHERE user_id=:uid AND state='aprobado' AND liquidation_id IS NULL
                      AND work_date<=:cutoff AND approval_at::date<=:cutoff FOR UPDATE'''),dict(uid=uid,cutoff=cutoff)).mappings().all()
                    if not records:raise ValueError('No hay HH pendientes para este corte.')
                    total_q=sum(r['quarters'] for r in records);amount=sum((r['quarters']*rate)//4 for r in records)
                    lid=c.execute(text('''INSERT INTO liquidations(user_id,period,cutoff_date,cents,quarters,created_by)
                        VALUES(:uid,:p,:cutoff,:amount,:q,:actor) RETURNING id'''),dict(uid=uid,p=cutoff.strftime('%Y-%m'),cutoff=cutoff,amount=amount,q=total_q,actor=u['id'])).scalar_one()
                    for record in records:
                        cents=record['quarters']*rate//4
                        c.execute(text('INSERT INTO liquidation_lines(liquidation_id,entry_id,quarters,rate_cents,amount_cents) VALUES(:lid,:eid,:q,:rate,:cents)'),dict(lid=lid,eid=record['id'],q=record['quarters'],rate=rate,cents=cents))
                        c.execute(text("UPDATE entries SET state='liquidado',liquidation_id=:lid WHERE id=:id"),dict(lid=lid,id=record['id']))
                    audit_event(c,'cerrar_liquidacion','liquidation',lid,f'Corte {cutoff}')
                st.success(f'Liquidación #{lid} cerrada: {money(amount)}');st.rerun()
            except Exception as exc:st.error(str(exc))
    st.subheader('Liquidaciones cerradas')
    closed=all_rows('''SELECT l.id,us.name,l.period,l.cutoff_date,l.quarters,l.cents,l.created_at
        FROM liquidations l JOIN users us ON us.id=l.user_id ORDER BY l.id DESC LIMIT 500''')
    df=pd.DataFrame([dict(ID=r['id'],Trabajador=r['name'],Periodo=r['period'],Corte=r['cutoff_date'],HH=r['quarters']/4,Total_Soles=r['cents']/100,Creada=r['created_at']) for r in closed])
    st.dataframe(df,hide_index=True,use_container_width=True)
    if not df.empty:
        buf=io.BytesIO()
        with pd.ExcelWriter(buf,engine='openpyxl') as writer:df.to_excel(writer,index=False,sheet_name='Liquidaciones')
        st.download_button('Exportar liquidaciones a Excel',data=buf.getvalue(),file_name='altivia_liquidaciones.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        pdf=io.BytesIO();cv=canvas.Canvas(pdf,pagesize=A4)
        cv.setFont('Helvetica-Bold',14);cv.drawString(42,800,'ALTIVIA - Liquidaciones cerradas');cv.setFont('Helvetica',9)
        y=773
        for _,r in df.head(55).iterrows():
            cv.drawString(42,y,f"#{r['ID']}  {str(r['Trabajador'])[:30]}   {r['HH']:.2f} HH    S/ {r['Total_Soles']:,.2f}")
            y-=13
            if y<45:cv.showPage();y=800
        cv.save()
        st.download_button('Exportar resumen a PDF',data=pdf.getvalue(),file_name='altivia_liquidaciones.pdf',mime='application/pdf')

elif page=='Auditoría':
    st.caption('Últimos 500 movimientos · utiliza la búsqueda de la tabla para localizar una acción o registro.')
    rows=all_rows('SELECT * FROM audit ORDER BY id DESC LIMIT 500')
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
