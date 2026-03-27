import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from waitress import serve
from src.webapp import create_app,db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    serve(app, host='0.0.0.0', port=5000)