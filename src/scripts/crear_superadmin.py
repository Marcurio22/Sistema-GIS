"""
crear_superadmin.py — crea o actualiza el superadmin de una instancia GIS.

Uso:
  python src/scripts/crear_superadmin.py --username admin --email admin@cr.local
  (contrasena en SUPERADMIN_PASSWORD o --password)
"""

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&.,#€])[A-Za-z\d@$!%*?&.,#€]{8,}$"
)


def find_project_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(15):
        if (cur / "data").exists() and (cur / "src").exists():
            return cur
        cur = cur.parent
    return Path.cwd().resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Crear o actualizar superadmin")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    password = args.password or os.getenv("SUPERADMIN_PASSWORD", "")
    if not password:
        print("ERROR: indica --password o la variable SUPERADMIN_PASSWORD.")
        return 1

    if not PASSWORD_PATTERN.match(password):
        print(
            "ERROR: la contraseña debe tener al menos 8 caracteres, "
            "incluir mayúscula, minúscula, número y carácter especial."
        )
        return 1

    project_root = find_project_root(Path(__file__).resolve().parent)
    load_dotenv(project_root / ".env", override=True)
    sys.path.insert(0, str(project_root / "src"))

    db_name = os.getenv("POSTGRES_DB") or os.getenv("DATABASE_URL", "")
    print(f"Conectando a BD: {db_name}")

    from webapp import create_app, db
    from webapp.models import User

    app = create_app()
    with app.app_context():
        existing_super = User.query.filter_by(rol="superadmin").first()
        by_username = User.query.filter_by(username=args.username).first()
        by_email = User.query.filter_by(email=args.email).first()

        if by_email and (not by_username or by_email.id_usuario != by_username.id_usuario):
            print(f"ERROR: el email {args.email} ya está en uso por otro usuario.")
            return 1

        if existing_super:
            user = existing_super
            if by_username and by_username.id_usuario != user.id_usuario:
                print(f"ERROR: el usuario {args.username} ya existe en otra cuenta.")
                return 1
            user.username = args.username
            user.email = args.email
            user.rol = "superadmin"
            user.activo = True
            user.set_password(password)
            action = "actualizado"
        elif by_username:
            user = by_username
            user.email = args.email
            user.rol = "superadmin"
            user.activo = True
            user.set_password(password)
            action = "actualizado"
        else:
            user = User(
                username=args.username,
                email=args.email,
                rol="superadmin",
                activo=True,
            )
            user.set_password(password)
            db.session.add(user)
            action = "creado"

        db.session.commit()
        print(f"Superadmin {action}: {user.username} <{user.email}>")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
