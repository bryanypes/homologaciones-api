from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", case_sensitive=True)

    # App
    APP_NAME: str = "Homologaciones API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str
    DATABASE_URL_ASYNC: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    RESET_PASSWORD_TOKEN_EXPIRE_MINUTES: int = 30  # Token de reset válido 30 minutos

    #Gemini
    OPENAI_API_KEY: str

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # Storage
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10
    BASE_URL: str = "http://localhost:8000"  # URL base para generar links de documentos

    # Email — Brevo (https://brevo.com, 300 correos/día gratis)
    BREVO_API_KEY: Optional[str] = None
    EMAIL_FROM: Optional[str] = None

    # Cloudflare R2 (opcional — si no se configura, usa disco local)
    R2_ACCOUNT_ID: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_BUCKET_NAME: Optional[str] = None

    # Email de mercadeo (notificación cuando una homologación es aprobada)
    MERCADEO_EMAIL: Optional[str] = None


settings = Settings()