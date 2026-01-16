-- Comprobar cuántos va a tocar
WITH recintos_sin_actual AS (
  SELECT id_recinto
  FROM public.cultivos
  GROUP BY id_recinto
  HAVING SUM(CASE WHEN id_padre IS NOT NULL THEN 1 ELSE 0 END) = 0
)
SELECT COUNT(*) AS recintos_afectados
FROM recintos_sin_actual;

--------------------------------------------------------------------------

-- Actualizar los cultivos que no tienen id_padre en cada recinto
WITH recintos_sin_actual AS (
  SELECT id_recinto
  FROM public.cultivos
  GROUP BY id_recinto
  HAVING SUM(CASE WHEN id_padre IS NOT NULL THEN 1 ELSE 0 END) = 0
),
candidato AS (
  SELECT DISTINCT ON (c.id_recinto)
         c.id_recinto, c.id_cultivo
  FROM public.cultivos c
  JOIN recintos_sin_actual r ON r.id_recinto = c.id_recinto
  ORDER BY c.id_recinto,
           COALESCE(c.fecha_siembra, c.fecha_implantacion) DESC,
           c.id_cultivo DESC
)
UPDATE public.cultivos c
SET id_padre = c.id_cultivo
FROM candidato x
WHERE c.id_cultivo = x.id_cultivo;
