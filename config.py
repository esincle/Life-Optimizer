import os


def _database_uri():
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        return "sqlite:///life_optimizer.db"
    # Some hosts give postgres://; SQLAlchemy wants postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


class Config:
    # Local fallback only — set SECRET_KEY in the published app’s secrets
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-local-only"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///life_optimizer.db"


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _database_uri()
