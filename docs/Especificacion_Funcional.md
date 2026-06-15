# Especificación Funcional — Oposiciones Zaragoza

## Resumen
- **Nombre:** Oposiciones Zaragoza — tracker de procesos selectivos del Ayuntamiento de Zaragoza.
- **Propósito:** Extraer, almacenar y presentar información de convocatorias y cuadros anuales desde zaragoza.es, ofrecer búsqueda, estadísticas y lectura de PDFs de bases.
- **Entrada/salida:** Scraper -> BD SQLite (`datos/oposiciones.db`) -> API REST -> Frontend Bootstrap.

**Referencias de código:** [app/__init__.py](app/__init__.py), [run.py](run.py), [README.md](README.md)

**Audiencia:** desarrolladores, mantenedores y operadores.

**Condición de ejecución:** Python 3.10+, dependencias en [requirements.txt](requirements.txt).

## Funcionalidades principales
- **Scraping completo:** descarga lista de procesos abiertos, detalle de cada ficha y cuadros anuales históricos.
- **Actualización bajo demanda:** botón en UI y endpoint `POST /api/scraping/iniciar`.
- **Historial de ejecuciones:** registro de cada scraping con duración, estado y errores.
- **Búsqueda y filtrado:** listado paginado (`/api/ofertas`), filtros por año, grupo, estado y búsqueda por texto (FTS5).
- **Lectura de PDFs:** descarga y extracción estructurada de temario, criterios y fechas (`/api/ofertas/<id>/pdf`).
- **Cronograma:** lectura y parseo del PDF de cronograma municipal y persistencia en BD.
- **Scheduler:** ejecución automática configurable (día/hora).
- **Frontend interactivo:** panel con estadísticas, tablas, filtros y panel de detalle (Bootstrap 5).

## Stack tecnológico
- **Lenguaje:** Python 3.10+
- **Framework web:** Flask (ver [app/__init__.py](app/__init__.py))
- **HTTP:** requests + BeautifulSoup4 (parsing con lxml)
- **PDF:** pdfplumber
- **Scheduler:** APScheduler
- **Base de datos:** SQLite con FTS5 para búsquedas (fichero `datos/oposiciones.db`)
- **Cache:** cachetools (usado en repositorios para TTL)
- **Tests:** pytest, pytest-flask
- **Frontend:** HTML + Bootstrap 5 + Bootstrap Icons (archivo [app/templates/index.html](app/templates/index.html))

Referencias: [requirements.txt](requirements.txt)

## Arquitectura y patrones
- **Application Factory:** `crear_app()` en [app/__init__.py](app/__init__.py) — facilita tests y configuraciones.
- **Repository Pattern:** acceso a datos centralizado en [app/repositories](app/repositories) — `OfertaRepository`, `LogRepository`, `CronogramaRepository`.
- **Facade Pattern:** `services/oferta_service.py` orquesta el scraping y coordina repositorios y logs.
- **Context Manager:** `obtener_conexion()` en [app/database/conexion.py](app/database/conexion.py) gestiona transacciones y cierre de conexión.
- **ThreadPoolExecutor:** scraping de detalles concurrente (4 hilos por defecto) en `oferta_service`.
- **FTS5 + triggers:** base de datos mantiene índices FTS sincronizados con triggers (ver [app/database/esquema.sql](app/database/esquema.sql)).

## Base de datos (resumen)
- **Motor:** SQLite (archivo en `datos/oposiciones.db`).
- **Tablas principales:** `oferta`, `anuncio`, `oferta_anual`, `log_scrape`, `cronograma`.
- **Búsqueda full-text:** `oferta_fts` y `oferta_anual_fts` usando FTS5 y triggers para mantener consistencia.
- **Índices:** por `anio`, `grupo`, `estado` y `es_activa` para consultas frecuentes.
- **Migraciones simples:** `_migrar_esquema()` añade columnas cuando faltan (ver [app/database/conexion.py](app/database/conexion.py)).
- **Integridad:** PRAGMA foreign_keys = ON; claves foráneas en `anuncio`.

Ver DDL completo: [app/database/esquema.sql](app/database/esquema.sql)

## Repositorios y acceso a datos
- **OfertaRepository:** inserta/actualiza ofertas (UPSERT), paginación, FTS5, estadísticas y frecuencia. (ver [app/repositories/oferta_repo.py](app/repositories/oferta_repo.py))
- **LogRepository:** crea/actualiza logs de scraping, añade errores y devuelve historial. (ver [app/repositories/log_repo.py](app/repositories/log_repo.py))
- **CronogramaRepository:** reemplaza y consulta entradas del cronograma (ver [app/repositories/cronograma_repo.py](app/repositories/cronograma_repo.py)).

Patrón: toda interacción SQL va por los repositorios; facilita cambio de motor en el futuro.

## Lógica de negocio y servicios
- **OfertaService (Facade):** controla estado global del scraping, ejecuta fases, registra progreso en BD, actualiza cachés e informa al frontend. Ejecuta el scraping en un hilo para no bloquear Flask. (ver [app/services/oferta_service.py](app/services/oferta_service.py))
- **Scraper:** responsable exclusivo de parsear HTML de zaragoza.es; funciones clave:
  - `obtener_procesos_abiertos()` — lista paginada y deduplicada.
  - `obtener_detalle_oferta(oferta_id)` — parseo de ficha y anuncios, normalización de URLs, detección de estado mediante heurísticas y dateparser.
  - `obtener_anios_disponibles()` y `obtener_cuadro_anual(anio)` — cuadros históricos.
  - Maneja codificación ISO-8859-1 y respeta pausas configurables entre requests.
  (ver [app/services/scraper.py](app/services/scraper.py))
- **PDF Service:** descarga y extrae temario, baremo, requisitos y fechas usando `pdfplumber`. Devuelve advertencias si el PDF es imagen/escaneado. (ver [app/services/pdf_service.py](app/services/pdf_service.py))
- **Scheduler:** inicia tareas periódicas configurables por día/hora; se integra con `crear_app()` y puede detenerse con `atexit`. (ver [app/__init__.py](app/__init__.py) y [app/services/scheduler.py](app/services/scheduler.py)).

## API REST
- **Prefix:** `/api` implementado en [app/api/rutas.py](app/api/rutas.py).
- **Principales endpoints:**
  - `GET /api/estado` — estado del scraping y estadísticas.
  - `POST /api/scraping/iniciar` — inicia scraping en background.
  - `GET /api/scraping/historial` — historial de ejecuciones.
  - `GET /api/activas` — procesos abiertos (filtros: grupo, estado, busqueda).
  - `GET /api/ofertas` — paginación, filtros y búsqueda FTS5.
  - `GET /api/ofertas/<id>` — detalle completo con anuncios.
  - `POST /api/ofertas/<id>/actualizar` — re-scrape de una oferta concreta.
  - `GET /api/ofertas/<id>/pdf` — leer y extraer contenido del PDF.
  - `GET /api/cronograma` y `POST /api/cronograma/actualizar` — cronograma municipal.
  - `GET /api/scheduler` — información del scheduler.

Errores y respuestas: estándar `{ok: true, datos: ...}` o `{ok: false, error: 'mensaje'}`; validaciones devuelven 400.

## Criterios y heurísticas importantes
- **Detección de estado**: heurísticas basadas en anuncios y parsing de fechas con `dateparser` (ver `_detectar_estado` en scraper).
- **Normalización de URLs:** `_completar_url` y post-procesos en DB para arreglar enlaces sin `/oferta/`.
- **Evitar duplicados:** deduplicado en memoria durante scraping y restricciones UNIQUE/UNIQUE(anio,nombre,oferta_id) en BD.
- **Scraping concurrente pero seguro:** cada hilo abre su propia conexión SQLite (context manager) para evitar conflictos.

## Logging
- **Estructura:** consola (nivel INFO) + fichero rotado (nivel DEBUG) con `RotatingFileHandler`.
- **Ubicación:** `logs/app.log` (creado automáticamente). Configuración en [app/__init__.py](app/__init__.py) y valores en [app/config.py](app/config.py).
- **Contenido:** mensajes de progreso, errores del scraper, registros críticos y detalles de excepciones (exc_info).
- **Historial de scraping en BD:** `log_scrape` permite mostrar errores y duración desde el frontend.

## Frontend y estilo visual
- **Framework:** Bootstrap 5, iconos con Bootstrap Icons.
- **Diseño:** paleta corporativa (variables CSS `--zgz-azul`, `--zgz-oro`), tarjetas de estadísticas, tablas paginadas, offcanvas para detalle.
- **Interacciones:** polling cada 3s a `/api/estado`, notificaciones toast, barra de progreso durante scraping.
- **Archivo principal:** [app/templates/index.html](app/templates/index.html).

## Caché y rendimiento
- **Cachetools:** repositorios usan decoradores `@cached` con TTL configurado (`cache_larga`, `cache_media`) para estadísticas y resultados costosos.
- **Paginación y FTS5:** reducen uso de memoria y aceleran búsquedas.
- **Scraping pausado y threads limitados:** respetar `PAUSA_ENTRE_REQUESTS` y `MAX_WORKERS=4` para no sobrecargar el servidor objetivo.

## Tests y calidad
- **Tests:** suite con pytest (ver README). Tests cubren validación, repositorios, scraper y API.
- **Configuración de desarrollo:** `FLASK_DEBUG`, `PORT` y `SCHEDULER_ACTIVO` en [app/config.py](app/config.py).

## Operación y despliegue
- **Ejecución local:** `python run.py` (o usar `PORT=... python run.py`).
- **Requisitos:** ver `requirements.txt`.
- **Datos persistentes:** `datos/oposiciones.db` y `logs/app.log` deben persistir entre reinicios.
- **Recomendaciones:** ejecutar en entorno virtual, hacer backups periódicos del `.db`, configurar un sistema de supervisión si se despliega en servidor.
