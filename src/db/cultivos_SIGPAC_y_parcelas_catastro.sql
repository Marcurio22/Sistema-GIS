-- Asegura PostGIS está disponible
CREATE EXTENSION IF NOT EXISTS postgis;

-- Schemas
CREATE SCHEMA IF NOT EXISTS sigpac;
CREATE SCHEMA IF NOT EXISTS catastro;

-- =========================
-- SIGPAC: Cultivos (gráfica)
-- =========================
CREATE TABLE IF NOT EXISTS sigpac.cultivos (
  id                   BIGINT PRIMARY KEY,
  dn_oid               BIGINT,

  provincia            INTEGER,
  municipio            INTEGER,
  agregado             INTEGER,
  zona                 INTEGER,
  poligono             INTEGER,
  parcela              INTEGER,
  recinto              INTEGER,

  exp_ca               INTEGER,
  exp_provincia        INTEGER,
  exp_num              INTEGER,

  parc_producto        INTEGER,
  parc_sistexp         TEXT,
  parc_supcult         BIGINT,
  parc_ayudasol        TEXT,
  pdr_rec              TEXT,

  cultsecun_producto   INTEGER,
  cultsecun_ayudasol   TEXT,

  parc_indcultapro     INTEGER,
  tipo_aprovecha       TEXT,

  geometry             geometry(MULTIPOLYGON, 4326)
);

CREATE INDEX IF NOT EXISTS cultivos_gix
  ON sigpac.cultivos USING GIST (geometry);

CREATE INDEX IF NOT EXISTS cultivos_sigpac_keys_ix
  ON sigpac.cultivos (provincia, municipio, poligono, parcela, recinto);

-- =========================
-- CATASTRO: Parcelas
-- =========================
CREATE TABLE IF NOT EXISTS catastro.parcelas (
  id            BIGSERIAL PRIMARY KEY,
  inspire_id    TEXT UNIQUE,        -- namespace:localId cuando esté disponible
  refcat        TEXT,               -- nationalCadastralReference (si viene)
  label         TEXT,
  area_m2       DOUBLE PRECISION,
  fecha_descarga TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
  geometry      geometry(MULTIPOLYGON, 4326)
);

CREATE INDEX IF NOT EXISTS parcelas_gix
  ON catastro.parcelas USING GIST (geometry);

CREATE INDEX IF NOT EXISTS parcelas_refcat_ix
  ON catastro.parcelas (refcat);