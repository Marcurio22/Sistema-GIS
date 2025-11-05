from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

load_dotenv()  # lee .env en la raíz del repo

engine = create_engine(os.getenv("DATABASE_URL"), future=True)

with engine.begin() as conn:
    v = conn.execute(text("SELECT PostGIS_Full_Version();")).scalar()
    print("OK PostGIS:", v)