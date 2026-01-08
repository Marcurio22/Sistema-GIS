-- 1) Renombrar
ALTER TABLE public.cultivos
  RENAME COLUMN id_parcela TO id_recinto;

-- 2) Añadir columnas base de PAC/SIGPAC
ALTER TABLE public.cultivos
  ADD COLUMN uso_sigpac char(2) NOT NULL,
  ADD COLUMN sistema_explotacion char(1) NOT NULL DEFAULT 'S', -- S=secano, R=regadío
  ADD COLUMN tipo_registro varchar(12) NOT NULL DEFAULT 'CAMPANA', -- CAMPANA | IMPLANTACION
  ADD COLUMN campana integer NULL,
  ADD COLUMN id_padre integer NULL,
  ADD COLUMN cod_producto integer NULL,            -- FEGA (si aplica)
  ADD COLUMN cultivo_custom varchar(120) NULL,     -- si no está en FEGA
  ADD COLUMN origen_cultivo char(1) NOT NULL DEFAULT 'F', -- F=FEGA, C=custom
  ADD COLUMN fecha_implantacion date NULL,         -- para IMPLANTACION (permanentes)
  ADD COLUMN fecha_cosecha_real date NULL,
  ADD COLUMN cosecha_estimada_auto boolean NOT NULL DEFAULT false;

-- 3) Quitar Kc de esta tabla (si existe)
ALTER TABLE public.cultivos
  DROP COLUMN IF EXISTS kc_cultivo;

-- 4) Constraints recomendados
ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_sistema_explotacion
    CHECK (sistema_explotacion IN ('S','R'));

ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_tipo_registro
    CHECK (tipo_registro IN ('CAMPANA','IMPLANTACION'));

ALTER TABLE public.cultivos
  ADD CONSTRAINT fk_cultivos_padre
    FOREIGN KEY (id_padre) REFERENCES public.cultivos(id_cultivo);

-- Origen FEGA vs Custom (evita nulos raros)
ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_origen_cultivo
    CHECK (
      (origen_cultivo = 'F' AND cod_producto IS NOT NULL AND cultivo_custom IS NULL)
      OR
      (origen_cultivo = 'C' AND cod_producto IS NULL AND cultivo_custom IS NOT NULL)
    );

-- Reglas mínimas por tipo de registro
ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_fechas_por_tipo
    CHECK (
      (tipo_registro = 'IMPLANTACION' AND fecha_implantacion IS NOT NULL AND campana IS NULL)
      OR
      (tipo_registro = 'CAMPANA' AND campana IS NOT NULL)
    );

-- (Opcional) limitar campana razonable
ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_campana_rango
    CHECK (campana IS NULL OR campana BETWEEN 2000 AND 2100);

-- 5) Índices útiles
CREATE INDEX IF NOT EXISTS idx_cultivos_recinto ON public.cultivos(id_recinto);
CREATE INDEX IF NOT EXISTS idx_cultivos_recinto_campana ON public.cultivos(id_recinto, campana);
CREATE INDEX IF NOT EXISTS idx_cultivos_cod_producto ON public.cultivos(cod_producto);

------------------------------------------------------------------------------------------------------------
-- 6) Estados del cultivo
-- Asegura default y no nulos (ajusta si ya tienes datos)
UPDATE public.cultivos
SET estado = 'planificado'
WHERE estado IS NULL OR estado = '';

ALTER TABLE public.cultivos
  ALTER COLUMN estado TYPE varchar(20),
  ALTER COLUMN estado SET DEFAULT 'planificado',
  ALTER COLUMN estado SET NOT NULL;

ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_estado_cultivo
  CHECK (estado IN ('planificado','implantado','en_curso','cosechado','abandonado'));

-- 7) Llaves foráneas
ALTER TABLE public.cultivos
  ADD CONSTRAINT fk_cultivos_uso_sigpac
  FOREIGN KEY (uso_sigpac) REFERENCES public.usos_sigpac(codigo);

ALTER TABLE public.cultivos
  ADD CONSTRAINT fk_cultivos_cod_producto
  FOREIGN KEY (cod_producto) REFERENCES public.productos_fega(codigo);

------ Otros checks útiles ------

-- Orden lógico de fechas (si se informan)
ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_orden_fechas
  CHECK (
    (fecha_siembra IS NULL OR fecha_cosecha_estimada IS NULL OR fecha_cosecha_estimada >= fecha_siembra)
    AND
    (fecha_siembra IS NULL OR fecha_cosecha_real IS NULL OR fecha_cosecha_real >= fecha_siembra)
  );

-- Si marcas "auto", que exista fecha estimada
ALTER TABLE public.cultivos
  ADD CONSTRAINT chk_auto_necesita_estimada
  CHECK (cosecha_estimada_auto = false OR fecha_cosecha_estimada IS NOT NULL);
------------------------------------------------------------------------------------------------------------
