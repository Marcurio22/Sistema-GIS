-- NOTA: De momento este trigger no se incluye en el update_cultivos.sql (NO LO USAMOS)
-- 1) Función del trigger
CREATE OR REPLACE FUNCTION public.trg_set_tipo_cultivo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  -- Normaliza origen (por si viene en minúscula)
  IF NEW.origen_cultivo IS NOT NULL THEN
    NEW.origen_cultivo := UPPER(NEW.origen_cultivo);
  END IF;

  -- Caso FEGA
  IF NEW.origen_cultivo = 'F' THEN
    IF NEW.cod_producto IS NULL THEN
      RAISE EXCEPTION 'origen_cultivo=F requiere cod_producto (no puede ser NULL)';
    END IF;

    -- Rellena tipo_cultivo desde el catálogo FEGA
    SELECT p.descripcion
      INTO NEW.tipo_cultivo
    FROM public.productos_fega p
    WHERE p.codigo = NEW.cod_producto;

    IF NEW.tipo_cultivo IS NULL THEN
      RAISE EXCEPTION 'cod_producto % no existe en productos_fega', NEW.cod_producto;
    END IF;

    -- Asegura que no quede cultivo_custom si es FEGA
    NEW.cultivo_custom := NULL;

  -- Caso CUSTOM
  ELSIF NEW.origen_cultivo = 'C' THEN
    IF NEW.cultivo_custom IS NULL OR BTRIM(NEW.cultivo_custom) = '' THEN
      RAISE EXCEPTION 'origen_cultivo=C requiere cultivo_custom (no puede ser NULL/vacío)';
    END IF;

    -- Rellena tipo_cultivo con el nombre custom
    NEW.tipo_cultivo := BTRIM(NEW.cultivo_custom);

    -- Asegura que no quede cod_producto si es custom
    NEW.cod_producto := NULL;

  ELSE
    RAISE EXCEPTION 'origen_cultivo inválido: %, esperado F o C', NEW.origen_cultivo;
  END IF;

  RETURN NEW;
END;
$$;

-- 2) Trigger (borra el anterior si ya existía)
DROP TRIGGER IF EXISTS set_tipo_cultivo_biud ON public.cultivos;

CREATE TRIGGER set_tipo_cultivo_biud
BEFORE INSERT OR UPDATE OF origen_cultivo, cod_producto, cultivo_custom
ON public.cultivos
FOR EACH ROW
EXECUTE FUNCTION public.trg_set_tipo_cultivo();
