-- Tabla puente SIGPAC -> id_parcela (usada por automatizacion_sigpac_7_dias.py)
-- No siempre viene en dumps schema-only de gisdb; el script la crea si falta.

CREATE TABLE IF NOT EXISTS public.parcelas (
    id_parcela     SERIAL PRIMARY KEY,
    nombre         VARCHAR(200) NOT NULL,
    superficie_ha  NUMERIC(12, 4),
    geom           geometry(MultiPolygon, 4326) NOT NULL,
    provincia      BIGINT NOT NULL,
    municipio      BIGINT NOT NULL,
    agregado       BIGINT,
    zona           BIGINT,
    poligono       BIGINT NOT NULL,
    recinto        BIGINT NOT NULL,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activa         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_parcelas_sigpac_keys
    ON public.parcelas (provincia, municipio, agregado, zona, poligono, recinto);

CREATE INDEX IF NOT EXISTS idx_parcelas_geom
    ON public.parcelas USING GIST (geom);
