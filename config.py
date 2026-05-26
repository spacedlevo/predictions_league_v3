import os


class Config:
    def __init__(self):
        self.SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
        # Local dev: set SQLITE_PATH to use SQLite
        # Production (PythonAnywhere): set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
        self.SQLITE_PATH = os.environ.get("SQLITE_PATH")
        self.DB_HOST = os.environ.get("DB_HOST")
        self.DB_USER = os.environ.get("DB_USER")
        self.DB_PASSWORD = os.environ.get("DB_PASSWORD")
        self.DB_NAME = os.environ.get("DB_NAME")
