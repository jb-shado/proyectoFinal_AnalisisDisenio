import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv() #carga el archivo .env

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")

    DB_USER = quote_plus( os.getenv('DB_USER','') )
    DB_PASS = quote_plus( os.getenv('DB_PASSWORD','') )
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = os.getenv('DB_PORT')
    DB_NAME = os.getenv('DB_NAME')


    SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    #el SECRET_KEY y DATABASE_URL son la variables del .env
