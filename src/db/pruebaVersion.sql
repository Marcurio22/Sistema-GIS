-- Crear rol de aplicación
--DROP ROLE IF EXISTS gis_user;
--CREATE ROLE gis_user LOGIN PASSWORD 'GIS1234';

-- Entrar a la BD y activar extensiones
--CREATE EXTENSION IF NOT EXISTS postgis;
--CREATE EXTENSION IF NOT EXISTS postgis_raster;

--Permisos mínimos sin SUPERUSER
--REVOKE ALL ON SCHEMA public FROM PUBLIC;
--GRANT USAGE ON SCHEMA public TO gis_user;

--ALTER DEFAULT PRIVILEGES IN SCHEMA public
 -- GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gis_user;

--ALTER DEFAULT PRIVILEGES IN SCHEMA public
 -- GRANT USAGE, SELECT ON SEQUENCES TO gis_user;

--Verificar versión y comprobación de efectuación correcta
SELECT version();
SELECT PostGIS_Full_Version();

