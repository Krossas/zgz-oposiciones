-- esquema.sql — Definición de todas las tablas de la base de datos.
--
-- Se usa SQLite, que no requiere instalar ningún servidor de base de datos.
-- El fichero .db que genera es portable: puedes abrirlo con herramientas
-- visuales como "DB Browser for SQLite" para inspeccionar los datos.


-- ── Tabla principal de ofertas ───────────────────────────────────────────────
-- Cada fila es una convocatoria/proceso selectivo del Ayuntamiento.
-- Los campos reflejan exactamente lo que muestra la ficha de zaragoza.es.
CREATE TABLE IF NOT EXISTS oferta (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    oferta_id        TEXT    UNIQUE NOT NULL,   -- ID numérico de la URL (?id=1739)
    nombre           TEXT,
    grupo            TEXT,                       -- A1, A2, B, C1, C2, E
    anio             INTEGER,
    turno            TEXT,                       -- Libre, Promoción Interna, etc.
    plantilla        TEXT,
    escala           TEXT,
    expediente       TEXT,
    plazas           TEXT,                       -- Se guarda como texto (puede incluir desglose)
    tipo_examen      TEXT,                       -- Oposición, Concurso-oposición, etc.
    titulacion       TEXT,
    observaciones    TEXT,
    convocatoria_bop TEXT,
    convocatoria_boe TEXT,
    fecha_instancia  TEXT,                       -- Fecha límite de presentación de instancias
    bases_url        TEXT,                       -- URL a las bases de la convocatoria
    url              TEXT,                       -- URL completa a la ficha en zaragoza.es
    estado           TEXT DEFAULT 'pendiente',   -- Ver servicio: detectar_estado()
    es_activa        INTEGER DEFAULT 0,          -- 1 si aparece en "Procesos abiertos"
    ultimo_scrape    TEXT,                       -- ISO 8601
    creado_en        TEXT DEFAULT (datetime('now')),
    actualizado_en   TEXT DEFAULT (datetime('now'))
);

-- ── Anuncios de cada oferta ───────────────────────────────────────────────────
-- Cada oferta tiene una sección "Anuncios" donde van apareciendo novedades:
-- bases publicadas, plazo de inscripción, lista de admitidos, fecha de examen...
-- Se guardan separados para poder filtrar y mostrar la progresión de cada proceso.
CREATE TABLE IF NOT EXISTS anuncio (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    oferta_id TEXT NOT NULL,
    fecha     TEXT,
    texto     TEXT,
    url       TEXT,
    FOREIGN KEY (oferta_id) REFERENCES oferta(oferta_id) ON DELETE CASCADE
);

-- ── Cuadros de ofertas anuales ────────────────────────────────────────────────
-- El Ayuntamiento publica cada año un "Cuadro de Ofertas" con TODAS las plazas
-- previstas, aunque muchas aún no tengan convocatoria publicada.
-- Esto permite el análisis de frecuencia histórica.
CREATE TABLE IF NOT EXISTS oferta_anual (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    anio         INTEGER NOT NULL,
    nombre       TEXT    NOT NULL,
    oferta_id    TEXT,                           -- Puede ser NULL si aún no hay ficha
    plazas       TEXT,
    grupo        TEXT,
    procedimiento TEXT,                          -- Oposición, Concurso, Concurso-oposición
    titulacion   TEXT,
    observaciones TEXT,
    url          TEXT,
    UNIQUE(anio, nombre, oferta_id)             -- Evitar duplicados al re-scrapear
);

-- ── Log de operaciones de scraping ────────────────────────────────────────────
-- Cada vez que se lanza un scraping completo se crea un registro.
-- Permite saber cuándo se actualizaron los datos, cuánto tardó y si hubo errores.
CREATE TABLE IF NOT EXISTS log_scrape (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    iniciado_en       TEXT    NOT NULL,
    finalizado_en     TEXT,
    estado            TEXT    DEFAULT 'en_curso',   -- 'en_curso', 'completado', 'error'
    ofertas_guardadas INTEGER DEFAULT 0,
    progreso          TEXT,                          -- Mensaje del paso actual
    errores           TEXT    DEFAULT '[]'           -- JSON array de mensajes de error
);

-- ── Índices para consultas frecuentes ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_oferta_activa  ON oferta(es_activa);
CREATE INDEX IF NOT EXISTS idx_oferta_anio    ON oferta(anio);
CREATE INDEX IF NOT EXISTS idx_oferta_grupo   ON oferta(grupo);
CREATE INDEX IF NOT EXISTS idx_oferta_estado  ON oferta(estado);
CREATE INDEX IF NOT EXISTS idx_anuncio_oferta ON anuncio(oferta_id);
CREATE INDEX IF NOT EXISTS idx_anual_anio     ON oferta_anual(anio);

-- ── Índice de búsqueda de texto completo (FTS5) ───────────────────────────────
-- FTS5 es el motor de búsqueda de texto completo incluido en SQLite.
-- Permite búsquedas por prefijo (admin*), frases exactas ("trabajo social")
-- y es tolerante a variaciones de capitalización.
-- Se mantiene sincronizado con la tabla oferta mediante triggers.
CREATE VIRTUAL TABLE IF NOT EXISTS oferta_fts USING fts5(
    oferta_id UNINDEXED,   -- No indexamos el ID, solo lo usamos para JOIN
    nombre,
    grupo       UNINDEXED,
    observaciones,
    titulacion,
    content='oferta',      -- Tabla origen para reconstrucción
    content_rowid='id'
);

-- Trigger: insertar en FTS cuando se inserta una oferta
CREATE TRIGGER IF NOT EXISTS oferta_fts_insert
AFTER INSERT ON oferta BEGIN
    INSERT INTO oferta_fts(rowid, oferta_id, nombre, grupo, observaciones, titulacion)
    VALUES (new.id, new.oferta_id, new.nombre, new.grupo, new.observaciones, new.titulacion);
END;

-- Trigger: actualizar FTS cuando se actualiza una oferta
CREATE TRIGGER IF NOT EXISTS oferta_fts_update
AFTER UPDATE ON oferta BEGIN
    INSERT INTO oferta_fts(oferta_fts, rowid, oferta_id, nombre, grupo, observaciones, titulacion)
    VALUES ('delete', old.id, old.oferta_id, old.nombre, old.grupo, old.observaciones, old.titulacion);
    INSERT INTO oferta_fts(rowid, oferta_id, nombre, grupo, observaciones, titulacion)
    VALUES (new.id, new.oferta_id, new.nombre, new.grupo, new.observaciones, new.titulacion);
END;

-- Trigger: borrar de FTS cuando se borra una oferta
CREATE TRIGGER IF NOT EXISTS oferta_fts_delete
AFTER DELETE ON oferta BEGIN
    INSERT INTO oferta_fts(oferta_fts, rowid, oferta_id, nombre, grupo, observaciones, titulacion)
    VALUES ('delete', old.id, old.oferta_id, old.nombre, old.grupo, old.observaciones, old.titulacion);
END;

-- Lo mismo para oferta_anual
CREATE VIRTUAL TABLE IF NOT EXISTS oferta_anual_fts USING fts5(
    id          UNINDEXED,
    nombre,
    titulacion,
    observaciones,
    content='oferta_anual',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS oferta_anual_fts_insert
AFTER INSERT ON oferta_anual BEGIN
    INSERT INTO oferta_anual_fts(rowid, id, nombre, titulacion, observaciones)
    VALUES (new.id, new.id, new.nombre, new.titulacion, new.observaciones);
END;

CREATE TRIGGER IF NOT EXISTS oferta_anual_fts_update
AFTER UPDATE ON oferta_anual BEGIN
    INSERT INTO oferta_anual_fts(oferta_anual_fts, rowid, id, nombre, titulacion, observaciones)
    VALUES ('delete', old.id, old.id, old.nombre, old.titulacion, old.observaciones);
    INSERT INTO oferta_anual_fts(rowid, id, nombre, titulacion, observaciones)
    VALUES (new.id, new.id, new.nombre, new.titulacion, new.observaciones);
END;

CREATE TRIGGER IF NOT EXISTS oferta_anual_fts_delete
AFTER DELETE ON oferta_anual BEGIN
    INSERT INTO oferta_anual_fts(oferta_anual_fts, rowid, id, nombre, titulacion, observaciones)
    VALUES ('delete', old.id, old.id, old.nombre, old.titulacion, old.observaciones);
END;

-- ── Cronograma de procesos ────────────────────────────────────────────────────
-- Datos extraídos del PDF de cronograma publicado por el Ayuntamiento.
-- Guarda la fecha prevista de cada fase de cada proceso.
CREATE TABLE IF NOT EXISTS cronograma (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    proceso        TEXT,
    fase           TEXT,
    fechas         TEXT,    -- JSON array de fechas encontradas
    texto_completo TEXT,
    actualizado_en TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cronograma_proceso ON cronograma(proceso);
