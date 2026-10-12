# ALTIVIA HH CONTROL — Streamlit + PostgreSQL

Conversión nativa de la aplicación v7 (Flask) a Streamlit. **No es compatible con el hosting local de SQLite para producción**. Se requiere una base PostgreSQL administrada, persistente y con copias de seguridad. El hosting web gratuito de Streamlit **no incluye** una base de datos persistente.

## Instalación en Streamlit Community Cloud

1. Crea una base PostgreSQL gestionada (por ejemplo, Neon o Supabase) con conexión TLS, política de respaldo y capacidad de conexiones adecuada. Verifica sus precios y límites vigentes.
2. Crea un repositorio privado en GitHub y sube **el contenido de esta carpeta**, incluyendo `app.py`, `db.py`, `requirements.txt` y `.streamlit/config.toml`. **No subas `altivia_hh.db`, `secrets.toml` real ni contraseñas.**
3. En Streamlit Community Cloud, selecciona repositorio, rama, y archivo principal `app.py`.
4. En *Advanced settings / Secrets*, agrega `DATABASE_URL = "postgresql://...?...sslmode=require"`. Reemplaza con tu cadena real (consulta `.streamlit/secrets.toml.example`). La base debe aceptar conexiones entrantes desde el servidor de Streamlit.
5. Publica la aplicación. En el primer inicio, registra al administrador con contraseña robusta.
6. Primero ensaya con usuarios de prueba. Después importa tu información o ejecuta la migración desde una copia SQLite, siguiendo las instrucciones de abajo.

> **IMPORTANTE:** Si el enlace de la app es públicamente accesible, cualquier persona puede intentar acceder al formulario de login. Utiliza base de datos privada, cuentas fuertes, controles de acceso corporativos cuando corresponda y evita exponer datos personales reales hasta completar una auditoría de seguridad. Streamlit Community Cloud no ofrece en esta app un aislamiento de usuarios equivalente a una plataforma empresarial administrada.

## Migrar datos de v7

Haz copia del archivo `altivia_hh.db` de la carpeta local anterior. Utiliza **PostgreSQL nuevo, vacío y dedicado** para probar la migración. Instala las dependencias de `requirements.txt` y ejecuta en tu PC:

```bash
set DATABASE_URL=postgresql://USUARIO:CLAVE@HOST:5432/DB?sslmode=require
python tools/migrate_v7_sqlite.py C:\ruta\a\copia_altivia_hh.db
```

La migración preserva IDs de usuarios, proyectos, actividades, asignaciones, registros, liquidaciones y líneas cerradas. Como la v7 almacenaba tarifas por fecha y esta versión usa tarifa estándar, la tarifa vigente más reciente pasa a ser la estándar; los importes de liquidaciones anteriores permanecen congelados. **No borres el SQLite original hasta validar los totales.**

## Funcionalidades

- Login y contraseña hashed, roles admin/supervisor/trabajador, cambio obligatorio de clave temporal.
- Dashboard por proyecto y fechas exactas; tarjetas de HH cargadas, aprobadas, pendientes y presupuesto.
- Proyectos con estado activo/desactivado/terminado y bloqueo de HH en los inactivos.
- Registro y corrección de HH; actividades según asignación.
- Aprobaciones y rechazo/observación por supervisor asignado o administrador, sin autoaprobación.
- Consolidado de HH por profesional y desglose opcional por actividad.
- Tabla de usuarios y tabla de actividades editables; tarifas estándar editables por trabajador.
- Importación EDT/HH de matriz Excel: hoja `Estimado de Costos`, fila 5 J:T profesionales, B código, C actividad. Se crean usuarios nuevos con contraseñas temporales aleatorias (no nombre, por seguridad cloud), mostradas al administrador al terminar la importación.
- Liquidaciones por fecha de corte, que solo incluyen HH aprobadas hasta esa fecha; línea única por HH y tarifa congelada por línea. Exportación a Excel y PDF.
- Auditoría de operaciones clave.

## Limitaciones que requieren validación antes de uso real

- No se han ejecutado pruebas end-to-end contra PostgreSQL/Streamlit Cloud; se verificó sintaxis, no funcionamiento en nube.
- No hay recuperación automática de contraseña, MFA ni inicio de sesión Microsoft 365. Los usuarios se autentican con claves propias en la aplicación.
- El alta inicial de administrador debe estar controlada; no dejes el portal abierto durante el primer inicio.
- Streamlit Community Cloud y proveedores PostgreSQL externos pueden tener suspensión por inactividad, límites y condiciones de servicio.
- No se implementó un subsistema de pagos bancarios ni permisos de aislamiento multiempresa. No utilizar como nómina legal automatizada.
- Los reportes PDF son resúmenes, no comprobantes contables o legales.
- Los presupuestos son totales por actividad; al filtrar fechas, el saldo comparativo es presupuesto total menos HH del rango, no saldo histórico.
- La importación permite actualizar la matriz de actividades salvo actividades con HH liquidadas; realizar respaldos previos.

## Seguridad mínima de operación

Crear usuarios con contraseñas aleatorias y rotación inicial. No compartir enlaces con secretos, no exponer la cadena DATABASE_URL, limitar acceso a repositorio y base, activar backup/PITR de la base según oferta del proveedor. Probar la aplicación y auditar permisos antes de uso real.
