ALTIVIA HH CONTROL - Windows
==========================
1. Instalar Python 3.10 o superior, marcando Add Python to PATH.
2. Extraer la carpeta completa en la PC.
3. Hacer doble clic en INICIAR_ALTIVIA.bat (primera vez requiere Internet para dependencias).
4. Abrir http://127.0.0.1:8765 si no se abre solo.
5. En el PRIMER INICIO crear la cuenta de administrador y su contraseña de al menos 10 caracteres.
6. Crear usuarios, proyectos, actividades, asignaciones y tarifas en Administracion.
7. Los usuarios registran HH y el supervisor o administrador aprueba.
8. Generar liquidaciones desde la seccion Liquidaciones.

IMPORTANTE:
- Base de datos: altivia_hh.db; respaldar regularmente toda la carpeta de datos con la APP CERRADA.
- El programa se ejecuta exclusivamente en 127.0.0.1 (solo esta PC) por seguridad.
- No habilitar acceso externo ni abrir puertos del router sin implementar HTTPS, servicio central y controles de seguridad adicionales.
- Para varios trabajadores desde sus celulares o laptops se requiere despliegue centralizado; la version local permite cuentas separadas desde el mismo equipo.
- No hay sincronizacion automatica con OneDrive/SharePoint.
- Los importes son estimaciones administrativas por horas aprobadas; considerar tributos/retenciones y contratos fuera del programa.
- No compartir la base SQLite entre varios ordenadores mediante carpeta sincronizada: existe riesgo de corrupcion.

LIMITACIONES DE ESTA PRIMERA VERSION:
- La app es un prototipo local para una PC; no incluye una instancia central multiusuario para acceso simultaneo remoto.
- No incluye Microsoft 365 SSO, SharePoint, alertas por correo, automatizaciones, pagos bancarios ni cambios de presupuesto despues de su creacion.
- No gestiona pagos parciales, impuestos, retenciones, anulaciones/reaperturas de liquidaciones ni aprobaciones escalonadas.
- Cada trabajador/periodo puede tener solamente una liquidacion; revisar todas las HH antes de cerrar.
- Las horas corregidas se revalidan al guardar, pero en esta version no recalculan el limite total diario incluyendo otros registros.
- Validar funcionamiento y revisar seguridad antes de utilizar datos personales o financieros reales.

NOVEDADES V2 (09/10/2026)
- Tarifas editables/eliminables desde Administración; bloqueadas cuando el trabajador tiene liquidaciones para proteger histórico. Primero respalde la base de datos.
- Fechas de corte para cada liquidación y cierres incrementales dentro del mismo mes. Ej.: corte 15/09 deja pendientes las HH posteriores o aún sin aprobar, que podrán liquidarse después.
- Nuevo portafolio de proyectos en Inicio; KPI consumido vs presupuestado y avance físico separado. El avance físico se administra como porcentaje por actividad en Administración.
- Administración > Importar Excel: interpreta la hoja Estimado de Costos de la matriz ALTIVIA: columna B código, columna C tarea, fila 5 columnas J:T nombres de profesionales, cruces positivos HH asignadas; TBD no es usuario.
- Para importar: crear antes los usuarios con nombres exactamente iguales a la fila 5 y crear el proyecto. Actividades importadas obtienen controles por cruce profesional+actividad. Si alguna actividad tiene HH ya liquidadas no se sobrescribe.
- Migración automática de antiguas bases SQLite para permitir varios cierres por trabajador/mes. Conserve SIEMPRE un respaldo de altivia_hh.db antes de iniciar esta versión.
- EXCEL: Se omiten encabezados resumen con códigos terminados en 000, para evitar sumar totales de agrupaciones como si fueran actividades.
AVISO: Aplicación local para un PC, no exponer el puerto 8765 a Internet. No se incluyen integraciones automáticas con SharePoint ni acceso móvil por Internet. Pruebas de ejecución de interfaz pendientes de validación en Windows.

ACTUALIZACION V2 - OCTUBRE 2026
--------------------------------
1. Cierra la aplicacion antes de actualizar.
2. Respaldar altivia_hh.db y secrets.json originales en una carpeta externa.
3. Descomprimir la V2 y copiar app.py, requirements.txt y el BAT sobre los de la carpeta actual.
4. NO sustituir ni borrar altivia_hh.db ni secrets.json de la instalacion existente.
5. Las migraciones se aplican automaticamente la proxima vez que inicies.
6. El modulo Liquidaciones permite elegir fecha de corte: solo incluye HH de fechas de trabajo
   y aprobacion anteriores o iguales al corte. Las HH no incluidas siguen disponibles
   para otra liquidacion del periodo. No incluye pagos bancarios.
7. En Administracion puedes editar o eliminar tarifas sin liquidaciones cerradas vinculadas;
   al existir liquidaciones la modificacion de tarifas queda bloqueada por integridad historica.
8. Importar Excel acepta la plantilla CMH/Puka Mani en hoja 'Estimado de Costos',
   nombres fila 5 (J:T), codigo EDT columna B, titulo columna C, cruces positivos HH.
   Primero crear en el modulo Usuarios a los profesionales con el nombre coincidente.
   El excel elegido NO se guarda en disco; sus asignaciones se copian a SQLite.
9. Cuando un proyecto contiene matriz importada, la actividad se restringe a los profesionales
   listados en los cruces positivos de la matriz. Registros previos no se borran.
10. Panel principal incluye consumo acumulado del presupuesto y avance fisico ponderado.
    El avance fisico se ingresa manualmente en Administracion; NO equivale a HH consumidas.
11. Version para PC local: no incluye acceso multiusuario remoto seguro, sincronizacion
    a SharePoint, ni confirmacion de pagos bancarios.

ACTUALIZACION V3 - TARIFA ESTANDAR Y HH POR PROFESIONAL
-------------------------------------------------------
- Administracion: una tarifa estandar por trabajador, sin fecha de vigencia visible.
- Guardar una tarifa ya existente la actualiza; ya no genera duplicados.
- La tabla de tarifas ahora permite guardar o quitar la tarifa del trabajador.
- Las liquidaciones historicas guardan tarifa e importe congelados, por lo que no se recalculan.
- ATENCION: la tarifa estandar actual se utiliza para TODAS las HH aun no liquidadas,
  incluso cuando las fechas de trabajo sean anteriores al cambio de tarifa.
  Si un cambio de tarifa no debe ser retroactivo, cierra las HH pendientes antes de editarla.
- Nueva pantalla 'HH por profesional' en navegacion y acciones rapidas: filtro por
  proyecto y mes, consolidado por trabajador y proyecto, estados y detalle desplegable
  por actividad.
- Quedan excluidos del consolidado los borradores, observados y rechazados.
- Se mantiene el corte de liquidacion por fecha de trabajo Y fecha de aprobacion.
- Si ya tienes instalada la v2, CIERRA la app y respalda altivia_hh.db y secrets.json.
  Copia los nuevos app.py, requirements.txt y BAT sobre los existentes, sin borrar datos.
- La sintaxis Python ha sido comprobada. Se requiere ejecutar una prueba funcional
  local en Windows antes de utilizar la version con pagos reales.


NOVEDADES V6 (octubre 2026)
- Dashboard filtrable por proyecto y mes; HH presupuestadas, cargadas y saldo simultáneos.
- Eliminado avance físico de la interfaz gerencial y administración; columna antigua conservada para compatibilidad SQLite.
- Usuarios editables en una tabla horizontal compacta.
- El trabajador elige proyecto y después actividad filtrada por proyecto.
- Rediseño global del estilo.
- Nunca reemplace altivia_hh.db ni secrets.json. Haga copia de seguridad y pruebe en carpeta clonada.
- Cifras del portafolio son acumuladas históricas; tarjetas de estados son del mes seleccionado.


VERSION 7 — Filtros y estados de proyectos
- Inicio: filtros independientes/combina­dos por proyecto, fecha inicial y final; sin fechas = histórico.
- Las HH por rango usan FECHA DE TRABAJO; el presupuesto es el presupuesto total.
- Administración > Gestionar actividades: cambia el estado del proyecto a Activo, Desactivado o Terminado.
- Proyectos no activos quedan excluidos de la selección de HH y de la validación de nuevos registros en servidor.
- Historial, auditoría y liquidaciones anteriores se conservan.
- Migración automática: columna projects.status; los proyectos antes activos siguen activos.
- Usa una copia de altivia_hh.db para probar primero; no reemplaces la base de datos ni secrets.json.
