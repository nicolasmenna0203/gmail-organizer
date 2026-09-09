# Política de privacidad — Gmail Organizer

**Última actualización:** 9 de septiembre de 2026

Gmail Organizer es una herramienta de automatización personal de código
abierto que organiza la bandeja de entrada de Gmail de su propio usuario.
No es un servicio: cada persona que la usa la instala en su propia cuenta
de GitHub, con sus propias credenciales.

## Qué datos accede la aplicación

La aplicación solicita el scope `https://www.googleapis.com/auth/gmail.modify`
de la API de Gmail, y con él lee y modifica únicamente la cuenta de correo
que autorizó el acceso. Concretamente, en cada ejecución lee:

- La dirección del remitente (`From`) y el asunto (`Subject`) de los
  correos sin etiquetar.
- Las etiquetas ya aplicadas a cada conversación.

Y en base a reglas de texto configuradas por el propio usuario:

- Aplica etiquetas.
- Archiva correos leídos antiguos.
- Envía a la papelera correos promocionales antiguos y correos de
  remitentes que el usuario listó explícitamente.

## Qué datos se almacenan

**Ninguno.** La aplicación no tiene servidor, base de datos ni
almacenamiento propio. Cada ejecución ocurre en un contenedor efímero de
GitHub Actions que se destruye al terminar.

- El contenido de los correos no se guarda, copia ni transmite a ningún
  lado.
- El token de acceso OAuth se guarda como *GitHub Secret* cifrado en el
  repositorio del propio usuario, y solo se usa para autenticarse contra
  la API de Gmail.
- Los registros de ejecución (logs de GitHub Actions) contienen únicamente
  contadores agregados (cuántos correos se etiquetaron, archivaron o
  borraron) y las direcciones de remitentes recurrentes que el usuario
  podría querer dar de baja.

## Con quién se comparten los datos

Con nadie. No hay terceros involucrados, no hay analítica, no hay
publicidad, no hay modelos de IA ni servicios externos procesando el
correo. La clasificación se hace con coincidencia de patrones de texto
ejecutada localmente en el contenedor.

Las únicas partes que intervienen técnicamente son Google (proveedor de
la API de Gmail) y GitHub (donde corre la automatización), ambas bajo sus
propias políticas de privacidad.

## Control y revocación

El usuario puede revocar el acceso de la aplicación en cualquier momento
desde https://myaccount.google.com/permissions, sin necesidad de
intervención del desarrollador. Al hacerlo, la automatización deja de
funcionar de inmediato.

## Código fuente

El código completo es público y auditable en
https://github.com/nicolasmenna0203/gmail-organizer

## Contacto

Para cualquier consulta sobre esta política: nicolasmenna10@gmail.com
