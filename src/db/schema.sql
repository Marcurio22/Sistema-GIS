-- 1) Extensiones recomendadas
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;

--------------------------------------------------
-- 2) TABLA DE USUARIOS
--------------------------------------------------
CREATE TABLE usuarios (
    id_usuario       SERIAL PRIMARY KEY,
    username         VARCHAR(50)  NOT NULL UNIQUE,
    password_hash    VARCHAR(255) NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    rol              VARCHAR(50)  NOT NULL,
    fecha_registro   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    activo           BOOLEAN      NOT NULL DEFAULT TRUE
);

--------------------------------------------------
-- 3) PARCELAS
--------------------------------------------------
CREATE TABLE parcelas (
    id_parcela     SERIAL PRIMARY KEY,
    nombre         VARCHAR(100) NOT NULL,
    superficie_ha  NUMERIC(10,4),
    geom           geometry(Polygon, 4326) NOT NULL,
    propietario    VARCHAR(100),
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activa         BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_parcelas_geom
    ON parcelas
    USING GIST (geom);

--------------------------------------------------
-- 4) CULTIVOS (ciclo de cultivo en una parcela)
--------------------------------------------------
CREATE TABLE cultivos (
    id_cultivo            SERIAL PRIMARY KEY,
    id_parcela            INTEGER NOT NULL REFERENCES parcelas(id_parcela) ON DELETE CASCADE,
    tipo_cultivo          VARCHAR(80) NOT NULL,   -- p.ej. maíz, olivo, almendro
    variedad              VARCHAR(80),
    fecha_siembra         DATE,
    fecha_cosecha_estimada DATE,
    estado                VARCHAR(50),            -- p.ej. "en crecimiento", "cosechado"
    kc_cultivo            NUMERIC(6,3)           -- coeficiente Kc medio / del cultivo
);

CREATE INDEX idx_cultivos_parcela
    ON cultivos(id_parcela);

--------------------------------------------------
-- 5) IMÁGENES SATELITALES (tipo Sentinel-2)
--------------------------------------------------
CREATE TABLE imagenes_satelitales (
    id_imagen          SERIAL PRIMARY KEY,
    satelite           VARCHAR(20)   NOT NULL,      -- S2A, S2B, Landsat, etc.
    fecha_adquisicion  DATE          NOT NULL,
    fecha_descarga     TIMESTAMPTZ,
    cobertura_nubes    NUMERIC(5,2),               -- porcentaje
    nivel_procesamiento VARCHAR(50),               -- L1C, L2A, etc.
    bbox               geometry(Polygon, 4326),    -- huella del producto
    ruta_archivo       TEXT          NOT NULL,     -- ruta/URI SAFE, ZIP, COG...
    producto_id        VARCHAR(120),               -- ID oficial del producto
    bandas_disponibles TEXT[]                      -- lista de bandas
);

CREATE INDEX idx_imagenes_sat_bbx
    ON imagenes_satelitales
    USING GIST (bbox);

--------------------------------------------------
-- 6) ÍNDICES RÁSTER (NDVI, ETP, etc.)
--------------------------------------------------
CREATE TABLE indices_raster (
    id_indice       SERIAL PRIMARY KEY,
    id_imagen       INTEGER NOT NULL REFERENCES imagenes_satelitales(id_imagen) ON DELETE CASCADE,
    id_parcela      INTEGER     REFERENCES parcelas(id_parcela) ON DELETE SET NULL,
    tipo_indice     VARCHAR(30) NOT NULL,          -- NDVI, ETP, LAI, NDWI...
    fecha_calculo   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valor_medio     NUMERIC(10,4),
    valor_min       NUMERIC(10,4),
    valor_max       NUMERIC(10,4),
    desviacion_std  NUMERIC(10,4),
    ruta_raster     TEXT,                          -- GeoTIFF / COG en disco u objeto
    raster_data     raster                         -- opcional: ráster dentro de BD
);

CREATE INDEX idx_indices_raster_tipo_fecha
    ON indices_raster(tipo_indice, fecha_calculo);

CREATE INDEX idx_indices_raster_parcela
    ON indices_raster(id_parcela);

--------------------------------------------------
-- 7) IMÁGENES DE DRON
--------------------------------------------------
CREATE TABLE imagenes_dron (
    id_imagen_dron       SERIAL PRIMARY KEY,
    id_parcela           INTEGER REFERENCES parcelas(id_parcela) ON DELETE SET NULL,
    fecha_vuelo          DATE,
    hora_vuelo           TIME,
    altitud_vuelo        NUMERIC(10,2),
    resolucion_espacial  NUMERIC(10,2),          -- m/pixel
    tipo_camara          VARCHAR(50),
    ruta_ortomosaico     TEXT,                   -- ruta a GeoTIFF/COG
    bbox                 geometry(Polygon, 4326)
);

CREATE INDEX idx_imagenes_dron_bbx
    ON imagenes_dron
    USING GIST (bbox);

--------------------------------------------------
-- 8) SENSORES EN CAMPO
--------------------------------------------------
CREATE TABLE sensores (
    id_sensor          SERIAL PRIMARY KEY,
    id_parcela         INTEGER REFERENCES parcelas(id_parcela) ON DELETE SET NULL,
    id_cultivo         INTEGER REFERENCES cultivos(id_cultivo) ON DELETE SET NULL,
    tipo_sensor        VARCHAR(50) NOT NULL,         -- humedad_suelo, meteo, etc.
    ubicacion          geometry(Point, 4326),
    fecha_instalacion  DATE,
    activo             BOOLEAN      NOT NULL DEFAULT TRUE,
    fabricante         VARCHAR(100),
    intervalo_medicion INTEGER                 -- minutos, por ejemplo
);

CREATE INDEX idx_sensores_parcela
    ON sensores(id_parcela);

CREATE INDEX idx_sensores_ubicacion
    ON sensores
    USING GIST (ubicacion);

--------------------------------------------------
-- 9) VARIABLES MEDIDAS POR LOS SENSORES
--    (tabla catálogo para normalizar las medidas)
--------------------------------------------------
CREATE TABLE variables (
    id_variable   SERIAL PRIMARY KEY,
    nombre        VARCHAR(60) NOT NULL UNIQUE,   -- humedad_suelo, temp_aire, precip, etc.
    unidad        VARCHAR(20) NOT NULL,          -- %, °C, mm, kPa, m3/h...
    descripcion   TEXT
);

--------------------------------------------------
-- 10) MEDICIONES DE SENSORES (serie temporal)
--------------------------------------------------
CREATE TABLE mediciones_sensores (
    id_medicion  BIGSERIAL PRIMARY KEY,
    id_sensor    INTEGER   NOT NULL REFERENCES sensores(id_sensor)  ON DELETE CASCADE,
    id_variable  INTEGER   NOT NULL REFERENCES variables(id_variable) ON DELETE CASCADE,
    fecha_hora   TIMESTAMPTZ NOT NULL,
    valor        NUMERIC(12,4) NOT NULL,
    otros_datos  JSONB
);

-- Una medida por sensor, variable y momento
CREATE UNIQUE INDEX uq_medicion_sensor_variable_ts
    ON mediciones_sensores(id_sensor, id_variable, fecha_hora);

CREATE INDEX idx_mediciones_ts
    ON mediciones_sensores(fecha_hora);

--------------------------------------------------
-- 11) RECOMENDACIONES DE RIEGO
--------------------------------------------------
CREATE TABLE recomendaciones_riego (
    id_recomendacion     SERIAL PRIMARY KEY,
    id_parcela           INTEGER NOT NULL REFERENCES parcelas(id_parcela) ON DELETE CASCADE,
    id_cultivo           INTEGER     REFERENCES cultivos(id_cultivo) ON DELETE SET NULL,
    fecha_recomendacion  TIMESTAMPTZ NOT NULL,
    necesidad_riego      VARCHAR(50),            -- texto corto (alta, media, baja…)
    mm_agua_recomendados NUMERIC(10,3),          -- lámina de riego recomendada
    fecha_proxima_revision DATE,
    base_calculo         TEXT,                   -- explicación / modelo / regla usada
    ndvi_promedio        NUMERIC(10,4),
    humedad_suelo        NUMERIC(10,4),
    etp_calculada        NUMERIC(10,4)
);

-- Opcional: evitar duplicados por día y parcela
CREATE UNIQUE INDEX uq_reco_parcela_fecha
    ON recomendaciones_riego(id_parcela, fecha_recomendacion::date);

--------------------------------------------------
-- 12) LOGS DEL SISTEMA / PIPELINE
--------------------------------------------------
CREATE TABLE logs_sistema (
    id_log            BIGSERIAL PRIMARY KEY,
    fecha_hora        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tipo_operacion    VARCHAR(50),      -- p.ej. 'descarga_sentinel', 'calculo_ndvi'
    modulo            VARCHAR(50),      -- 'ingesta', 'api', 'frontend', etc.
    nivel             VARCHAR(20),      -- INFO, WARN, ERROR
    mensaje           TEXT,
    datos_adicionales JSONB
);

CREATE INDEX idx_logs_fecha
    ON logs_sistema(fecha_hora);

CREATE INDEX idx_logs_modulo_nivel
    ON logs_sistema(modulo, nivel);
