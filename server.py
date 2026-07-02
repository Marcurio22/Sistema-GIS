import io
import os
import sys

from dotenv import load_dotenv
from waitress import serve

from src.webapp import create_app, db


# stdout/stderr en UTF-8 (útil en Windows Server)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Cargar .env desde el AppDirectory (NSSM) / cwd
load_dotenv()

HOST = os.getenv("FLASK_HOST", "0.0.0.0")
PORT = int(os.getenv("FLASK_PORT", "5000"))

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    serve(app, host=HOST, port=PORT)