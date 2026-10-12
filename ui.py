"""ALTIVIA presentation components. No writes to business storage."""
from html import escape
from pathlib import Path
import base64
import streamlit as st

ROOT = Path(__file__).parent
LOGO = ROOT / 'assets' / 'altivia-logo.png'
DESCRIPTIONS = {
    'Centro gerencial': ('Visión general de tus proyectos', 'Consulta el presupuesto, las horas registradas y las revisiones pendientes de tu equipo.'),
    'Mis HH': ('Registro de trabajo', 'Registra tus horas, consulta su estado y corrige las observaciones.'),
    'HH por profesional': ('Equipo y dedicación', 'Consulta la dedicación de cada profesional por proyecto y periodo.'),
    'Aprobaciones': ('Bandeja de aprobaciones', 'Revisa el detalle de cada registro y decide si aprobar, observar o rechazar.'),
    'Presupuestos EDT': ('Control de presupuestos EDT', 'Compara las horas previstas con el consumo de cada actividad.'),
    'Proyectos y actividades': ('Gestión de proyectos', 'Organiza proyectos, responsables, actividades y presupuestos.'),
    'Usuarios y tarifas': ('Equipo y tarifas', 'Administra accesos, tarifas por hora y actividades autorizadas.'),
    'Importar Excel': ('Importar matriz de presupuestos', 'Carga tu matriz EDT, revisa la vista previa y confirma la importación.'),
    'Liquidaciones': ('Cierre y liquidación', 'Convierte las horas aprobadas en un cierre verificable por profesional.'),
    'Auditoría': ('Trazabilidad', 'Consulta quién realizó cada cambio y cuándo ocurrió.'),
}
ICONS = ['◫', '◷', '◉', '✓', '▥', '▦', '♙', '↥', '▤', '≡']
NAV_ICONS = dict(zip(DESCRIPTIONS, ICONS))
DESCRIPTIONS.update({
    'Registrar horas': ('Registrar mis horas', 'Selecciona tu proyecto y actividad, e indica el trabajo realizado.'),
    'Mi historial': ('Mi historial de horas', 'Consulta tus registros, su estado de revisión y las observaciones recibidas.'),
})
NAV_ICONS.update({'Registrar horas': '＋', 'Mi historial': '◷'})
EYEBROWS = {
    'Centro gerencial': 'RESUMEN EJECUTIVO', 'Mis HH': 'REGISTRO PERSONAL',
    'Registrar horas': 'REGISTRO PERSONAL', 'Mi historial': 'HISTORIAL PERSONAL',
    'HH por profesional': 'ANÁLISIS DEL EQUIPO', 'Aprobaciones': 'SUPERVISIÓN · FLUJO DE REVISIÓN',
    'Presupuestos EDT': 'PRESUPUESTOS · EDT/WBS', 'Proyectos y actividades': 'PLANIFICACIÓN DE PROYECTOS',
    'Usuarios y tarifas': 'ADMINISTRACIÓN DEL EQUIPO', 'Importar Excel': 'IMPORTACIÓN · EXCEL',
    'Liquidaciones': 'CIERRE DEL PERIODO', 'Auditoría': 'CONTROL Y TRAZABILIDAD',
}

def apply_theme():
    st.markdown((ROOT / 'assets' / 'theme.css').read_text(encoding='utf-8'), unsafe_allow_html=True)

def brand(sidebar=False):
    target = st.sidebar if sidebar else st
    encoded = base64.b64encode(LOGO.read_bytes()).decode()
    target.markdown(f'<div class="brand"><img src="data:image/png;base64,{encoded}" alt="ALTIVIA Constructores"><div class="brand-label">ALTIVIA <span>CONTROL DE HORAS</span></div></div>', unsafe_allow_html=True)

def sidebar_identity(user):
    roles={'admin':'Administrador','supervisor':'Supervisor','trabajador':'Trabajador'}
    st.sidebar.markdown(f'<div class="sidebar-identity"><strong>{escape(user["name"])}</strong><span>{roles.get(user["role"],escape(user["role"]))}</span></div>',unsafe_allow_html=True)

def page_header(page, user):
    title, subtitle = DESCRIPTIONS[page]
    st.markdown(f'<div class="page-header"><div class="eyebrow">{EYEBROWS[page]}</div><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)

def login_intro():
    brand()
    st.markdown('<div class="login-hero"><div class="eyebrow">PLATAFORMA DEL EQUIPO</div><h1>ALTIVIA<br>Control de horas</h1><p>Un espacio para registrar el trabajo realizado, consultar su estado y coordinar nuestros proyectos.</p><div class="login-features"><span>Registro de actividades</span><span>Seguimiento de tus envíos</span><span>Colaboración con tu equipo</span></div></div>', unsafe_allow_html=True)

def empty_state(title, text, icon='◫'):
    st.markdown(f'<div class="empty-state"><div class="empty-icon">{escape(icon)}</div><strong>{escape(title)}</strong><p>{escape(text)}</p></div>',unsafe_allow_html=True)

def go(page):
    st.session_state['navigation'] = page

def shortcut(label, page, key, help=None):
    st.button(label, key=key, on_click=go, args=(page,), use_container_width=True, help=help)

def section_note(title, text):
    st.markdown(f'<div class="section-note"><strong>{escape(title)}</strong><span>{escape(text)}</span></div>', unsafe_allow_html=True)

def project_card(project, budget, used, approved, pending):
    ratio = used / budget * 100 if budget else 0
    tone = 'danger' if used > budget else ('warning' if ratio >= 80 else 'healthy')
    state = 'Sobre presupuesto' if used > budget else ('Próximo al límite' if ratio >= 80 else ('Sin presupuesto' if not budget else 'Dentro del presupuesto'))
    st.markdown(f'''<article class="project-card"><div class="project-top"><span class="project-code">{escape(project['code'])}</span><span class="status {tone}">{state}</span></div><h3>{escape(project['name'])}</h3><div class="project-figures"><strong>{used:,.2f}<small> HH registradas</small></strong><span>de {budget:,.2f} HH</span></div><div class="progress-track"><div class="progress-fill {tone}" style="width:{min(max(ratio,0),100):.2f}%"></div></div><div class="project-bottom"><span>{approved:,.2f} HH aprobadas</span><span>{pending:,.2f} HH pendientes</span></div></article>''', unsafe_allow_html=True)
