# ALTIVIA HH CONTROL — Streamlit v8 / SharePoint Lists

Conserva usuarios y roles, proyectos, EDT y presupuestos, asignaciones, HH, aprobaciones sin autoaprobación, tarifas, importación Excel, liquidaciones con tarifas congeladas y exportación Excel/PDF. Graph autentica al servidor con una aplicación Entra de un solo tenant. Los usuarios siguen usando sus cuentas ALTIVIA; esta migración no introduce SSO de Microsoft.

## Instalación

1. Conceder a la aplicación únicamente Graph **Application / Sites.Selected** y asignar `write` exclusivamente al sitio privado dedicado. El consentimiento global no da acceso a sitios por sí solo.
2. Registrar un certificado público en Entra. Conservar la clave privada fuera del repositorio y guardarla solo en la configuración privada del servidor. Ver `.streamlit/secrets.toml.example`.
3. Aprovisionar las 13 listas con `python tools/sharepoint_admin.py provision`, usando una identidad administrativa que pueda crear listas. Retirar permisos administrativos temporales al terminar. La app de ejecución necesita solo lectura/escritura en el sitio.
4. Ejecutar `streamlit run app.py`. Para una instalación vacía, habilitar temporalmente `ALTIVIA_SETUP_TOKEN`, crear el primer administrador usando esa clave y retirarla después. Si se migraron usuarios, sus cuentas se conservan.
5. En Streamlit Cloud seleccionar la rama validada y `app.py`; guardar configuración en **Settings → Secrets**, nunca en GitHub. Respaldar y validar antes de cambiar una aplicación en producción.

Configuración mediante variables de entorno, archivo JSON externo indicado por `ALTIVIA_CONFIG`, o Streamlit Secrets. Proveedor predeterminado: `sharepoint`. `DATA_BACKEND="postgresql"` conserva el proveedor anterior como alternativa; no sincroniza ambos almacenes. Su referencia histórica está en `README-postgresql.md`.

## Almacenamiento y operaciones completas

Listas: `HH_Usuarios`, `HH_Proyectos`, `HH_Actividades`, `HH_AsignacionesProyecto`, `HH_AsignacionesActividad`, `HH_Tarifas`, `HH_RegistrosHH`, `HH_Liquidaciones`, `HH_DetalleLiquidaciones`, `HH_Auditoria`, `HH_Importaciones`, `HH_Transacciones`, `HH_Control`.

Cada entidad guarda revisiones con clave única, JSON, operación y resumen legible. Las revisiones anteriores permanecen en SharePoint. **Editar únicamente mediante la app**: el estado confirmado se reconstruye y valida; restringir escrituras del sitio a la aplicación y administradores responsables.

SharePoint no tiene transacciones entre listas. Se escriben todas las revisiones y luego se publica una referencia única en `HH_Control` con `If-Match`/ETag. Si otro usuario confirmó antes, se rechaza la operación y debe repetirse tras actualizar. Una interrupción antes de publicar deja revisiones no visibles, evitando liquidaciones parcialmente confirmadas. Las importaciones grandes usan manifiestos fragmentados. No hay borrado físico.

Las consultas v8 se ejecutan con SQLite **solo en memoria** durante cada operación. SharePoint es el único almacenamiento persistente de este proveedor. Los arranques fríos leen el historial paginado: un historial grande aumenta memoria y tiempo de arranque. Medir con la carga real antes de crecer; no incluye compactación automática.

## Respaldo y migración sin sobrescritura

Los respaldos contienen hashes de usuarios y datos comerciales: conservar fuera de GitHub, en una ubicación privada.

```text
python tools/sharepoint_admin.py export-postgres --file /ruta/privada/origen.json
python tools/sharepoint_admin.py import-empty --file /ruta/privada/origen.json
python tools/sharepoint_admin.py backup --file /ruta/privada/sharepoint.json
python tools/sharepoint_admin.py check
```

La exportación usa una transacción consistente de solo lectura. La importación exige destino vacío, comprueba integridad y referencias, conserva IDs e importes y verifica la lectura posterior. No modifica PostgreSQL. Antes del corte detener escrituras en el origen, exportar el respaldo definitivo y comparar usuarios, presupuestos, HH por estado e importes. Mantener origen y respaldo hasta validar. La herramienta v7 anterior sigue disponible.

## Pruebas

```text
python -m pip install -r requirements.txt pytest
python -m pytest -q
python tools/sharepoint_smoke.py
```

Las pruebas locales cubren conflictos, interrupciones, respuesta perdida, integridad, importaciones grandes, límite de 12 HH, liquidaciones y pantallas por rol. La prueba real usa solo datos sintéticos inactivos en `HH_TEST_`, comprueba lectura desde otra instancia y rechazo HTTP 412 de ETag antiguo. Requiere listas preaprovisionadas y credencial válida. No elimina registros de prueba ni sustituye la validación del despliegue o la migración real.

## Comportamiento conservado

Tarifa estándar congelada por línea al liquidar. Presupuesto total por actividad aunque se filtren fechas. Excel: hoja `Estimado de Costos`, profesionales J:T/fila 5, códigos/actividades B/C. Liquidaciones internas con reportes, sin integración bancaria. Recuperación de acceso mediante restablecimiento por un administrador; sin recuperación por correo ni MFA para usuarios locales.
# Interfaz profesional ALTIVIA

La plataforma usa el logo corporativo y la paleta ALTIVIA: azul `#13364A`, turquesa `#077E78`, gris claro `#E7EEF4` y blanco. El inicio muestra «ALTIVIA · Control de horas». El centro gerencial muestra presupuesto, horas registradas, aprobadas y pendientes, tarjetas por proyecto y accesos directos a las acciones del administrador. Los filtros del reporte no limitan la bandeja de aprobación.

El rol **trabajador** tiene únicamente **Registrar horas** y **Mi historial**. No accede al centro gerencial, presupuestos proyectados, tarifas ni registros de otros profesionales. La navegación se valida en el servidor para impedir acceso mediante un estado de sesión antiguo. El historial muestra las horas propias y su estado, y permite corregir las observaciones.

En **Usuarios y tarifas**, utiliza las pestañas **Usuarios y accesos**, **Tarifas por hora** y **Asignaciones**. En **Proyectos y actividades**, los datos del proyecto y la edición del presupuesto se organizan en pestañas independientes. La guía del administrador está disponible en el centro gerencial.

Para actualizar esta interfaz, conserva juntos `app.py`, `ui.py`, `assets/` y `.streamlit/config.toml`, además de los módulos de almacenamiento. Las credenciales siguen en la configuración privada de Streamlit. El rediseño no requiere migrar listas ni modificar registros existentes.

## Administración de colaboradores

- **Crear colaborador:** ingresa nombres, primer apellido y otros apellidos. El usuario es el primer nombre en minúsculas y sin tildes; se agrega un número si está ocupado. La contraseña inicial es el primer apellido en minúsculas, sin tildes ni espacios, incluso si tiene menos de seis caracteres. El primer ingreso obliga a elegir una contraseña nueva de seis caracteres como mínimo. Esta regla se aplica a cuentas nuevas, no cambia cuentas existentes.
- **Importar Excel:** revisa y corrige la separación de nombres/apellidos en la tabla de nuevos colaboradores antes de confirmar. Las propuestas automáticas no distinguen todos los nombres o apellidos compuestos. Las cuentas ya existentes conservan usuario y contraseña.
- **Restablecer contraseña:** en Usuarios y accesos, selecciona otro colaborador y confirma una contraseña temporal de al menos seis caracteres. Se invalidan sus sesiones en la siguiente interacción y se exige un cambio al ingresar. La auditoría no incluye contraseñas.
- **Asignaciones:** selecciona un colaborador para consultar sus actividades de todos los proyectos; luego elige un proyecto, agrega o retira actividades y guarda. Las selecciones existentes aparecen marcadas. Retirar autorizaciones conserva las horas registradas; conservar una asignación mantiene sus horas planificadas. Puedes retirar también el acceso completo al proyecto.
- **Proyectos y actividades:** desactiva, termina o reactiva un proyecto desde Datos del proyecto. Para desactivar actividades, desmarca Activa y guarda la tabla. Las restricciones de registro y corrección se aplican por estado del proyecto/actividad; el historial se conserva.
- **Eliminar usuario / proyecto:** disponible solo para administradores en Usuarios y accesos y Datos del proyecto, respectivamente. Selecciona el registro y marca su confirmación antes de eliminar. La eliminación es recuperable: bloquea el acceso o nuevas horas y retira el registro de las listas operativas; conserva horas, actividades, presupuestos, tarifas, asignaciones, liquidaciones y auditoría. No puedes eliminar tu propia cuenta ni el último administrador activo. Los nombres de usuario y códigos quedan reservados para evitar mezclar historiales.
- **Recuperación:** abre Usuarios eliminados o Proyectos eliminados en su página administrativa. Los usuarios se recuperan inactivos y los proyectos desactivados; reactívalos expresamente cuando corresponda. Los informes históricos y liquidaciones conservan referencias a registros eliminados. Los registros anteriores de SharePoint se cargan con `deleted=0` sin migración destructiva.

`python tools/admin_smoke.py` comprueba estas operaciones contra Graph exclusivamente en las listas `HH_TEST_`, ya aprovisionadas. Crea datos ficticios, verifica una lectura desde otra instancia y desactiva las cuentas de prueba al finalizar. Conserva los registros para auditoría; no escribe en las listas de producción `HH_`.

