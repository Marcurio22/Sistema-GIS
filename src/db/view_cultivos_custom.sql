CREATE OR REPLACE VIEW public.catalogo_cultivos_selector AS
SELECT
  'F'::char(1) AS origen_cultivo,
  p.codigo     AS cod_producto,
  NULL::text   AS cultivo_custom,
  p.descripcion
FROM public.productos_fega p

UNION ALL
SELECT 'C', NULL, 'ALTRAMUZ', 'ALTRAMUZ'
UNION ALL
SELECT 'C', NULL, 'ALTRAMUZ DULCE', 'ALTRAMUZ DULCE';