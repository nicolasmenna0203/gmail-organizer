# Gmail Organizer

Automatización de bandeja de entrada de Gmail basada en reglas, que corre
a diario vía GitHub Actions — sin disparo manual, sin servidor que
mantener, sin llamadas a IA/LLM (y por lo tanto sin costo ni latencia por
ejecución).

Todos los días:

1. **Envía a la papelera** los correos de remitentes de los que ya te
   diste de baja pero que igual siguen escribiendo.
2. **Etiqueta** hilos sin etiquetar usando reglas configurables de patrones
   de remitente/asunto (hasta 250 hilos por corrida).
3. **Archiva** correos leídos antiguos (3+ meses) que no estén destacados,
   marcados como importantes, ni etiquetados como personales.
4. **Envía a la papelera** promociones antiguas (6+ meses) que no estén
   protegidas por una etiqueta más importante.
5. **Reporta** remitentes que aparecen 3+ veces en Promociones pero
   todavía no están en tu lista de baja — candidatos para el paso 1.

## Por qué reglas en vez de un clasificador con LLM

El vocabulario de remitentes/asuntos de una bandeja de entrada es chico y
repetitivo — los mismos 20-30 remitentes generan la mayor parte del
volumen. Una lista corta de reglas por substring y palabra clave clasifica
ese tráfico en milisegundos, gratis, con un resultado totalmente
predecible. Una llamada a un LLM por hilo agregaría latencia, costo y
no-determinismo a un problema que el pattern matching ya resuelve.

## Arquitectura

```
setup_auth.py         flujo OAuth de una sola vez → imprime el token JSON
gmail_organizer.py     el job diario (pasos 1-5 de arriba)
config.json             labels / reglas / lista de baja reales (gitignored)
config.example.json     misma estructura, con datos de ejemplo
.github/workflows/      disparo por cron + credenciales vía secrets
```

Tres secrets manejan la GitHub Action:

| Secret | Propósito |
|---|---|
| `GMAIL_TOKEN_JSON` | Token OAuth (access + refresh). Se refresca solo y se reescribe en el secret cuando expira — no hace falta volver a autenticar manualmente una vez configurado. |
| `GMAIL_ORGANIZER_CONFIG_JSON` | El contenido de `config.json`, así los datos personales (IDs de labels, lista de baja, reglas de etiquetado) nunca viven en el repo. |
| `GH_PAT` | PAT fine-grained con permiso de escritura sobre secrets, para que el workflow pueda reescribir `GMAIL_TOKEN_JSON` cuando se refresca. |

El script en sí es completamente genérico — todo lo específico de esta
bandeja en particular (qué remitentes confiar, qué labels existen, qué
cuenta como "financiero") vive en `config.json`, no en el código. Ese
archivo nunca se commitea: en producción lo escribe el workflow a partir
del secret `GMAIL_ORGANIZER_CONFIG_JSON` en cada corrida.

## Configuración

1. **Google Cloud Console**: creá un proyecto, habilitá la Gmail API,
   creá un OAuth Client ID (tipo Desktop app), descargá el JSON como
   `credentials.json`. Agregate como test user en la pantalla de
   consentimiento OAuth si la app no está verificada.

2. **Autenticación local**:
   ```bash
   pip install -r requirements.txt
   python setup_auth.py
   ```
   Esto abre el navegador para autorizar y luego imprime un token JSON.

3. **Configurar**: copiá `config.example.json` a `config.json` y completá
   tus IDs reales de labels de Gmail (los podés ver con el método
   `labels.list` de la Gmail API), tu lista de baja, y tus reglas de
   etiquetado.

4. **Secrets de GitHub** (Settings → Secrets and variables → Actions):
   - `GMAIL_TOKEN_JSON` — el token JSON del paso 2
   - `GMAIL_ORGANIZER_CONFIG_JSON` — el contenido de tu `config.json`
   - `GH_PAT` — un PAT de tipo fine-grained, limitado a este repo, con
     permiso **Secrets: Read and write**

5. Hacé push y después dispará el workflow manualmente una vez
   (`workflow_dispatch`) para confirmar que corre limpio antes de
   confiarle el cron diario.

## Ejemplo de salida

```
=== Gmail Organizer ===

▶ Paso 0: Trashing unsubscribed senders...
  Trashed: 3

▶ Paso 1: Tagging unlabeled threads (up to 250)...
  Personal: 214
  Promotions: 6
  Accounts & Security: 5
  Total tagged: 225

▶ Paso 2: Archiving old read emails...
  Archived: 12

▶ Paso 3: Trashing old promotions...
  Trashed: 4

▶ Paso 4: Unsubscribe candidates...
  newsletter@example.com (15 mails)
  promo@example-store.com (5 mails)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tagged: 225 | Archived: 12 | Trashed: 7
Unsubscribe candidates: 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Notas de seguridad

- Lo que se envía a la papelera queda en la Papelera de Gmail,
  recuperable por 30 días — nada se borra permanentemente de forma
  inmediata.
- Los hilos destacados o marcados como importantes siempre se saltean en
  todos los pasos destructivos.
- Cada paso tiene un tope por corrida (50-250 hilos) para mantener el uso
  de la API predecible y evitar rate limits.
- Ningún dato personal (remitentes reales, IDs de labels, credenciales)
  vive en este repositorio: todo entra vía GitHub Secrets en tiempo de
  ejecución.
