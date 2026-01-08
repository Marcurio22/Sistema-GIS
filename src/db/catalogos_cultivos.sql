CREATE TABLE IF NOT EXISTS public.productos_fega (
  codigo integer PRIMARY KEY,
  descripcion text NOT NULL
);

CREATE TABLE IF NOT EXISTS public.usos_sigpac (
  codigo char(2) PRIMARY KEY,
  descripcion text NOT NULL,
  grupo text NOT NULL
);