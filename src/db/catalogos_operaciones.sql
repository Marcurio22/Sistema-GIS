BEGIN;

CREATE TABLE IF NOT EXISTS public.catalogos_operaciones (
  catalogo        TEXT NOT NULL,
  codigo          TEXT NOT NULL,
  codigo_padre    TEXT NOT NULL DEFAULT '',
  nombre          TEXT NOT NULL,
  descripcion     TEXT NULL,
  fecha_baja      DATE NULL,
  fuente          TEXT NOT NULL DEFAULT 'SIEX_CIRCULAR_PAC_4_2025',
  extra           JSONB NOT NULL DEFAULT '{}'::jsonb,

  PRIMARY KEY (catalogo, codigo, codigo_padre)
);

CREATE INDEX IF NOT EXISTS idx_catops_catalogo
  ON public.catalogos_operaciones (catalogo);

CREATE INDEX IF NOT EXISTS idx_catops_catalogo_padre
  ON public.catalogos_operaciones (catalogo, codigo_padre);

-- Para búsquedas por nombre (typeahead)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_catops_nombre_trgm
  ON public.catalogos_operaciones USING GIN (nombre gin_trgm_ops);

COMMIT;