# 🏛️ Oposiciones Ayuntamiento de Zaragoza

Tracker de procesos selectivos del Ayuntamiento de Zaragoza.
Extrae datos de zaragoza.es, los almacena en SQLite y ofrece un panel web.

## Resumen rápido
- Lenguaje: Python 3.10+
- Web: Flask
- DB: SQLite (FTS5)
- Frontend: Bootstrap 5

Ver la especificación funcional completa: [docs/Especificacion_Funcional.md](docs/Especificacion_Funcional.md)

## Requisitos

- Python 3.10 o superior
- Conexión a Internet (para scraping)

## Instalación y ejecución (Windows / Linux)

```powershell
# Crear y activar entorno virtual (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

```bash
# Linux / macOS
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Abre http://localhost:5000 en tu navegador.

## Variables de entorno importantes

- `PORT` — puerto del servidor (por defecto: 5000)
- `FLASK_DEBUG` — `true` para modo debug
- `SCHEDULER_ACTIVO` — `true`/`false` para activar el scheduler automático
- `SCHEDULER_DIA`, `SCHEDULER_HORA` — día/hora de ejecución automática

Ejemplo (Linux/macOS):
```bash
PORT=8080 FLASK_DEBUG=true python run.py
```

## Primer uso

1. Abre la aplicación en el navegador.
2. Pulsa "Actualizar datos" para lanzar el scraping completo.
3. La primera ejecución puede tardar varios minutos (descarga histórica).
4. Datos persistidos en `datos/oposiciones.db` y logs en `logs/app.log`.

## Estructura del proyecto

```
zgz-oposiciones/
├── run.py
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database/
│   │   ├── conexion.py
│   │   └── esquema.sql
│   ├── repositories/
│   ├── services/
│   ├── api/
│   └── templates/
├── datos/          # Base de datos SQLite (persistente)
└── logs/           # Ficheros de log
```

## API REST (resumen)

- `GET /api/estado` — estado y estadísticas
- `POST /api/scraping/iniciar` — inicia scraping en background
- `GET /api/scraping/historial` — historial de ejecuciones
- `GET /api/activas` — procesos abiertos (filtros: grupo, estado, busqueda)
- `GET /api/ofertas` — listado paginado y filtrable
- `GET /api/ofertas/<id>` — detalle de una oferta
- `GET /api/ofertas/<id>/pdf` — leer/extractar PDF de bases

Para la lista completa de endpoints ver `app/api/rutas.py`.

## Logs y base de datos

- Logs: `logs/app.log` (consola INFO, fichero DEBUG, rotación automática).
- BD: `datos/oposiciones.db` (SQLite). Puedes abrirla con DB Browser for SQLite.

## Tests

```bash
python -m pytest -v
```

Los tests usan bases temporales y no modifican la base de datos principal.
