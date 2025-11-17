-- Crear base de datos gisdb (ejecutar este bloque una sola vez conectados)
CREATE DATABASE gisdb;
-- A continuación, conecta a la base de datos gisdb antes de ejecutar el resto del script.
-- En psql: \c gisdb

-- =========================================================
-- Extensiones necesarias
-- =========================================================
CREATE EXTENSION IF NOT EXISTS postgis;

-- =========================================================
-- USUARIOS
-- =========================================================
CREATE TABLE usuarios (
    id_usuario       SERIAL PRIMARY KEY,
    username         VARCHAR(50)  NOT NULL UNIQUE,
    password_hash    VARCHAR(255) NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    rol              VARCHAR(50)  NOT NULL,
    fecha_registro   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    activo           BOOLEAN      NOT NULL DEFAULT TRUE
);

-- =========================================================
-- PARCELAS
-- =========================================================
CREATE TABLE parcelas (
    id_parcela     SERIAL PRIMARY KEY,
    nombre         VARCHAR(100) NOT NULL,
    superficie_ha  NUMERIC(10,4),
    geom           geometry(Polygon, 4326) NOT NULL,
    propietario    VARCHAR(100),
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activa         BOOLEAN     NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_parcelas_geom ON parcelas USING GIST (geom);

-- =========================================================
-- CULTIVOS
-- =========================================================
CREATE TABLE cultivos (
    id_cultivo             SERIAL PRIMARY KEY,
    id_parcela             INTEGER NOT NULL REFERENCES parcelas(id_parcela) ON DELETE CASCADE,
    tipo_cultivo           VARCHAR(80) NOT NULL,
    variedad               VARCHAR(80),
    fecha_siembra          DATE,
    fecha_cosecha_estimada DATE,
    estado                 VARCHAR(50),
    kc_cultivo             NUMERIC(6,3)
);
CREATE INDEX idx_cultivos_parcela ON cultivos(id_parcela);

-- =========================================================
-- IMAGENES (PADRE COMÚN)
-- =========================================================
CREATE TABLE imagenes (
    id_imagen          SERIAL PRIMARY KEY,
    origen             VARCHAR(20) NOT NULL CHECK (origen IN ('satelite','dron')),
    fecha_adquisicion  TIMESTAMPTZ NOT NULL,
    epsg               INTEGER,                 -- EPSG del dataset original
    sensor             VARCHAR(80),             -- plataforma/cámara
    resolucion_m       NUMERIC(10,2),           -- resolución nativa (m)
    bbox               geometry(Polygon, 4326), -- footprint reproyectado a 4326
    ruta_archivo       TEXT NOT NULL            -- ruta/URI GeoTIFF/SAFE/COG
);
CREATE INDEX idx_imagenes_bbox ON imagenes USING GIST (bbox);
CREATE INDEX idx_imagenes_origen_fecha ON imagenes(origen, fecha_adquisicion);

-- =========================================================
-- IMAGENES_SATELITALES (HIJA 1:1)
-- =========================================================
CREATE TABLE imagenes_satelitales (
    id_imagen           INTEGER PRIMARY KEY REFERENCES imagenes(id_imagen) ON DELETE CASCADE,
    satelite            VARCHAR(20)   NOT NULL,  -- S2A, S2B, Landsat, etc.
    cobertura_nubes     NUMERIC(5,2),
    nivel_procesamiento VARCHAR(50),             -- L1C, L2A...
    producto_id         VARCHAR(120),
    bandas_disponibles  TEXT[]
);

-- =========================================================
-- IMAGENES_DRON (HIJA 1:1)
-- =========================================================
CREATE TABLE imagenes_dron (
    id_imagen          INTEGER PRIMARY KEY REFERENCES imagenes(id_imagen) ON DELETE CASCADE,
    id_parcela         INTEGER REFERENCES parcelas(id_parcela) ON DELETE SET NULL,
    hora_vuelo         TIME,
    altitud_vuelo      NUMERIC(10,2),
    resolucion_espacial NUMERIC(10,2),
    tipo_camara        VARCHAR(50)
);
CREATE INDEX idx_imagenes_dron_parcela ON imagenes_dron(id_parcela);

-- =========================================================
-- INDICES_RASTER (derivados de IMAGENES; opcionalmente por parcela)
-- =========================================================
CREATE TABLE indices_raster (
    id_indice       SERIAL PRIMARY KEY,
    id_imagen       INTEGER NOT NULL REFERENCES imagenes(id_imagen) ON DELETE CASCADE,
    id_parcela      INTEGER     REFERENCES parcelas(id_parcela) ON DELETE SET NULL,
    tipo_indice     VARCHAR(30) NOT NULL,       -- NDVI, ETP, LAI, NDWI...
    fecha_calculo   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    epsg            INTEGER,                    -- EPSG del ráster resultante (si difiere)
    resolucion_m    NUMERIC(10,2),              -- resolución del índice (m)
    valor_medio     NUMERIC(10,4),
    valor_min       NUMERIC(10,4),
    valor_max       NUMERIC(10,4),
    desviacion_std  NUMERIC(10,4),
    ruta_raster     TEXT NOT NULL               -- GeoTIFF/COG; no se almacena raster en BD
);
CREATE INDEX idx_indices_por_imagen ON indices_raster(id_imagen);
CREATE INDEX idx_indices_tipo_fecha ON indices_raster(tipo_indice, fecha_calculo);
CREATE INDEX idx_indices_parcela ON indices_raster(id_parcela);

-- =========================================================
-- SENSORES
-- =========================================================
CREATE TABLE sensores (
    id_sensor          SERIAL PRIMARY KEY,
    id_parcela         INTEGER REFERENCES parcelas(id_parcela) ON DELETE SET NULL,
    id_cultivo         INTEGER REFERENCES cultivos(id_cultivo) ON DELETE SET NULL,
    tipo_sensor        VARCHAR(50) NOT NULL,        -- humedad_suelo, meteo, etc.
    ubicacion          geometry(Point, 4326),
    fecha_instalacion  DATE,
    activo             BOOLEAN      NOT NULL DEFAULT TRUE,
    fabricante         VARCHAR(100),
    intervalo_medicion INTEGER
);
CREATE INDEX idx_sensores_parcela   ON sensores(id_parcela);
CREATE INDEX idx_sensores_ubicacion ON sensores USING GIST (ubicacion);

-- =========================================================
-- VARIABLES medidas por sensores
-- =========================================================
CREATE TABLE variables (
    id_variable   SERIAL PRIMARY KEY,
    nombre        VARCHAR(60) NOT NULL UNIQUE,   -- humedad_suelo, temp_aire, precip...
    unidad        VARCHAR(20) NOT NULL,
    descripcion   TEXT
);

-- =========================================================
-- MEDICIONES_SENSORES (serie temporal)
-- =========================================================
CREATE TABLE mediciones_sensores (
    id_medicion  BIGSERIAL PRIMARY KEY,
    id_sensor    INTEGER   NOT NULL REFERENCES sensores(id_sensor)   ON DELETE CASCADE,
    id_variable  INTEGER   NOT NULL REFERENCES variables(id_variable) ON DELETE CASCADE,
    fecha_hora   TIMESTAMPTZ NOT NULL,
    valor        NUMERIC(12,4) NOT NULL,
    otros_datos  JSONB
);
CREATE UNIQUE INDEX uq_med_sensor_var_ts ON mediciones_sensores(id_sensor, id_variable, fecha_hora);
CREATE INDEX idx_mediciones_ts ON mediciones_sensores(fecha_hora);

-- =========================================================
-- RECOMENDACIONES_RIEGO
-- =========================================================
CREATE TABLE recomendaciones_riego (
    id_recomendacion     SERIAL PRIMARY KEY,
    id_parcela           INTEGER NOT NULL REFERENCES parcelas(id_parcela) ON DELETE CASCADE,
    id_cultivo           INTEGER     REFERENCES cultivos(id_cultivo) ON DELETE SET NULL,
    fecha_recomendacion  TIMESTAMPTZ NOT NULL,
    necesidad_riego      VARCHAR(50),
    mm_agua_recomendados NUMERIC(10,3),
    fecha_proxima_revision DATE,
    base_calculo         TEXT,
    ndvi_promedio        NUMERIC(10,4),
    humedad_suelo        NUMERIC(10,4),
    etp_calculada        NUMERIC(10,4)
);
CREATE UNIQUE INDEX uq_reco_parcela_fecha ON recomendaciones_riego(id_parcela, ((fecha_recomendacion at time zone 'UTC')::date));

-- =========================================================
-- LOGS_SISTEMA
-- =========================================================
CREATE TABLE logs_sistema (
    id_log            BIGSERIAL PRIMARY KEY,
    id_usuario        INTEGER REFERENCES usuarios(id_usuario),
    fecha_hora        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tipo_operacion    VARCHAR(50),
    modulo            VARCHAR(50),
    nivel             VARCHAR(20),
    mensaje           TEXT,
    datos_adicionales JSONB
);
CREATE INDEX idx_logs_fecha ON logs_sistema(fecha_hora);
CREATE INDEX idx_logs_modulo_nivel ON logs_sistema(modulo, nivel);
