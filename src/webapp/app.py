from . import create_app, db

app = create_app()

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    with app.app_context():
        db.create_all()  
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)