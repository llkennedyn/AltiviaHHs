"""Server-side page permissions for ALTIVIA roles."""
def pages_for_role(role):
    if role == 'trabajador':
        return ['Registrar horas', 'Mi historial']
    pages = ['Centro gerencial', 'Mis HH', 'HH por profesional', 'Aprobaciones', 'Presupuestos EDT']
    if role == 'admin':
        return pages + ['Proyectos y actividades', 'Usuarios y tarifas', 'Importar Excel', 'Liquidaciones', 'Auditoría']
    return pages if role == 'supervisor' else []
