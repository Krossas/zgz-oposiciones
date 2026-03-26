# 🏛️ Oposiciones Ayuntamiento de Zaragoza

Tracker de oposiciones del Ayuntamiento de Zaragoza.
Scraping automático de zaragoza.es, base de datos SQLite local y panel web con Bootstrap.

## Requisitos

- Python 3.10 o superior (comprueba con `python --version` o `python3 --version`)
- Conexión a Internet (para el scraping)

## Instalación

```bash
# 1. Descomprime el proyecto
tar -xzf zgz-oposiciones.tar.gz
cd zgz-oposiciones

# 2. (Opcional pero recomendado) Crear un entorno virtual
python -m venv venv
source venv/bin/activate        # Linux / Mac
venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Arrancar
python run.py
```

Abre http://localhost:5000 en el navegador.

## Primer uso

1. Abre http://localhost:5000
2. Haz clic en **"Actualizar datos"** (esquina superior derecha)
3. Espera ~5-15 minutos (la primera vez descarga toda la información histórica)
4. Los datos quedan en `datos/oposiciones.db` — no necesitas repetir el proceso
   a menos que quieras actualizar la información

## Estructura del proyecto

```
zgz-oposiciones/
├── run.py                          ← Punto de entrada: python run.py
├── requirements.txt                ← Dependencias Python
├── app/
│   ├── __init__.py                 ← Factoría Flask (Application Factory)
│   ├── config.py                   ← Configuración centralizada
│   ├── database/
│   │   ├── conexion.py             ← Gestión de conexión SQLite
│   │   └── esquema.sql             ← Definición de tablas
│   ├── repositories/
│   │   ├── oferta_repo.py          ← Acceso a datos de ofertas (Repository Pattern)
│   │   └── log_repo.py             ← Acceso a logs de scraping
│   ├── services/
│   │   ├── scraper.py              ← Lógica de scraping de zaragoza.es
│   │   └── oferta_service.py       ← Orquestación del proceso (Facade Pattern)
│   ├── api/
│   │   └── rutas.py                ← Endpoints REST Flask
│   └── templates/
│       └── index.html              ← Frontend Bootstrap 5
├── datos/
│   └── oposiciones.db              ← Base de datos SQLite (se crea sola)
└── logs/
    └── app.log                     ← Log rotado (se crea solo)
```

## API REST disponible

| Método | Endpoint                          | Descripción                        |
|--------|-----------------------------------|------------------------------------|
| GET    | `/api/estado`                     | Estado del sistema y estadísticas  |
| POST   | `/api/scraping/iniciar`           | Lanza el scraping completo         |
| GET    | `/api/scraping/historial`         | Historial de scrapings             |
| GET    | `/api/activas`                    | Procesos actualmente abiertos      |
| GET    | `/api/ofertas`                    | Todas las fichas (filtros: anio, grupo, estado, busqueda) |
| GET    | `/api/ofertas/<id>`               | Detalle de una ficha con anuncios  |
| POST   | `/api/ofertas/<id>/actualizar`    | Re-scrape de una ficha concreta    |
| GET    | `/api/anuales?anio=2025`          | Cuadro de ofertas de un año        |
| GET    | `/api/anios`                      | Años disponibles                   |
| GET    | `/api/frecuencia`                 | Análisis de frecuencia por puesto  |
| GET    | `/api/estadisticas`               | Resumen estadístico                |

## Logs

Los logs se guardan en `logs/app.log`:
- **Consola**: nivel INFO (mensajes principales)
- **Fichero**: nivel DEBUG (todo el detalle, incluyendo cada petición)
- Rotación automática: cuando llega a 5 MB se crea un nuevo fichero,
  conservando hasta 3 copias históricas

## Base de datos

Puedes inspeccionar la base de datos con [DB Browser for SQLite](https://sqlitebrowser.org/)
(aplicación gratuita), abriendo el fichero `datos/oposiciones.db`.

## Cambiar el puerto

```bash
PORT=8080 python run.py
```

## Ejecutar los tests

```bash
python -m pytest tests/ -v
```

Los tests usan una base de datos temporal y no afectan a los datos reales.
Cubren: validación de parámetros, repositorios, scraper, API y caché.

## Mejoras técnicas incluidas

- **Búsqueda FTS5**: SQLite Full Text Search — insensible a mayúsculas,
  búsqueda por prefijo (`admin` encuentra `Administrativo`)
- **Scraping concurrente**: pool de 4 hilos paralelos, scraping ~4x más rápido
- **Caché**: respuestas de frecuencia y estadísticas cacheadas (TTL 5-60 min)
- **Paginación**: `/api/ofertas` devuelve páginas con metadatos
- **Validación**: todos los parámetros validados con errores HTTP 400 legibles
- **Cronograma**: lee el PDF del calendario del Ayuntamiento
- **95 tests** cubriendo todas las capas
