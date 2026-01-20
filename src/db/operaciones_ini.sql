BEGIN;

-- =========================================================
-- 1) Catálogo de tipos de operación
-- =========================================================
CREATE TABLE IF NOT EXISTS public.tipos_operacion (
  id_tipo_operacion SMALLSERIAL PRIMARY KEY,
  codigo VARCHAR(32) NOT NULL UNIQUE,
  descripcion TEXT NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- Valores iniciales
INSERT INTO public.tipos_operacion (codigo, descripcion)
VALUES
  ('RIEGO', 'Riego'),
  ('FERTILIZACION', 'Fertilización'),
  ('FITOSANITARIO', 'Tratamiento fitosanitario'),
  ('LABOREO', 'Laboreo / manejo del suelo'),
  ('SIEMBRA', 'Siembra / plantación'),
  ('RECOLECCION', 'Recolección / cosecha')
ON CONFLICT (codigo) DO NOTHING;


-- =========================================================
-- 2) Cabecera común de operaciones
-- =========================================================
CREATE TABLE IF NOT EXISTS public.operaciones (
  id_operacion BIGSERIAL PRIMARY KEY,

  id_recinto INTEGER NOT NULL
    REFERENCES public.recintos (id_recinto)
    ON DELETE CASCADE,

  id_tipo_operacion SMALLINT NOT NULL
    REFERENCES public.tipos_operacion (id_tipo_operacion),

  -- Fecha "principal" para ordenar/filtrar histórico
  fecha DATE NOT NULL,

  descripcion TEXT,

  -- JSONB para datos extra no normalizados
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices recomendados para histórico rápido
CREATE INDEX IF NOT EXISTS idx_operaciones_recinto_fecha
  ON public.operaciones (id_recinto, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_operaciones_tipo_fecha
  ON public.operaciones (id_tipo_operacion, fecha DESC);

-- Para búsquedas por meta si lo usas en el futuro
CREATE INDEX IF NOT EXISTS idx_operaciones_meta_gin
  ON public.operaciones USING GIN (meta);


-- =========================================================
-- 3) Subtabla: RIEGO
-- =========================================================
CREATE TABLE IF NOT EXISTS public.operaciones_riego (
  id_operacion BIGINT PRIMARY KEY
    REFERENCES public.operaciones (id_operacion)
    ON DELETE CASCADE,

  fecha_inicio TIMESTAMPTZ,
  fecha_fin TIMESTAMPTZ,

  volumen_m3 NUMERIC(12, 2),
  duracion_horas NUMERIC(8, 2),

  sistema_riego VARCHAR(32),
  procedencia_agua VARCHAR(32),

  -- Validaciones básicas
  CONSTRAINT chk_riego_fechas
    CHECK (fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio),

  CONSTRAINT chk_riego_valores
    CHECK (
      (volumen_m3 IS NULL OR volumen_m3 >= 0)
      AND (duracion_horas IS NULL OR duracion_horas >= 0)
    )
);


-- =========================================================
-- 4) Subtabla: FERTILIZACIÓN
-- =========================================================
CREATE TABLE IF NOT EXISTS public.operaciones_fertilizacion (
  id_operacion BIGINT PRIMARY KEY
    REFERENCES public.operaciones (id_operacion)
    ON DELETE CASCADE,

  producto TEXT NOT NULL,
  tipo_aplicacion VARCHAR(24),
  cantidad NUMERIC(12, 3) NOT NULL,
  unidad VARCHAR(16) NOT NULL DEFAULT 'kg',

  -- Nutrientes si quieres empezar a preparar balances
  n_total_kg NUMERIC(12, 3),
  p2o5_kg NUMERIC(12, 3),
  k2o_kg NUMERIC(12, 3),

  volumen_agua_m3 NUMERIC(12, 2),
  ce_dS_m NUMERIC(10, 3),

  CONSTRAINT chk_fert_cantidad
    CHECK (cantidad >= 0),

  CONSTRAINT chk_fert_npk
    CHECK (
      (n_total_kg IS NULL OR n_total_kg >= 0)
      AND (p2o5_kg IS NULL OR p2o5_kg >= 0)
      AND (k2o_kg IS NULL OR k2o_kg >= 0)
      AND (volumen_agua_m3 IS NULL OR volumen_agua_m3 >= 0)
      AND (ce_dS_m IS NULL OR ce_dS_m >= 0)
    )
);


-- =========================================================
-- 5) Subtabla: FITOSANITARIO
-- =========================================================
CREATE TABLE IF NOT EXISTS public.operaciones_fitosanitario (
  id_operacion BIGINT PRIMARY KEY
    REFERENCES public.operaciones (id_operacion)
    ON DELETE CASCADE,

  plaga_objetivo TEXT,
  producto_comercial TEXT NOT NULL,
  numero_registro VARCHAR(64),

  dosis NUMERIC(12, 3),
  unidad_dosis VARCHAR(16),
  volumen_caldo_l_ha NUMERIC(12, 2),

  plazo_seguridad_dias INTEGER,

  aplicador TEXT,
  maquinaria TEXT,

  temp_c NUMERIC(6, 2),
  viento_kmh NUMERIC(6, 2),
  lluvia BOOLEAN,

  CONSTRAINT chk_fitos_vals
    CHECK (
      (dosis IS NULL OR dosis >= 0)
      AND (volumen_caldo_l_ha IS NULL OR volumen_caldo_l_ha >= 0)
      AND (plazo_seguridad_dias IS NULL OR plazo_seguridad_dias >= 0)
      AND (temp_c IS NULL OR temp_c > -50 AND temp_c < 80)
      AND (viento_kmh IS NULL OR viento_kmh >= 0)
    )
);


-- =========================================================
-- 6) Trigger simple para updated_at en cabecera
-- =========================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_operaciones_updated_at ON public.operaciones;

CREATE TRIGGER trg_operaciones_updated_at
BEFORE UPDATE ON public.operaciones
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

COMMIT;