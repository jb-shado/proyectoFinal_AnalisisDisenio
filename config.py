import os
from dotenv import load_dotenv

load_dotenv() #carga el archivo .env

class Config:
    #SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    #SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    #SQLALCHEMY_TRACK_MODIFICATIONS = False
    pass
    #el SECRET_KEY y DATABASE_URL son la variables del .env