# config.py
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_very_secret_and_complex_key_2025'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///canteen.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt_super_secret_key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
