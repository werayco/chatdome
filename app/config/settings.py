from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    REDIS_URL: str
    SECRET_KEY: str
    PORT: str
    REDIS_URL: str
    GLITCHTIP_DOMAIN: str
    DEFAULT_FROM_EMAIL: str
    EMAIL_URL: str
    GLITCHTIP_DSN: str

    class Config:
        env_file = ".env"

settings = Settings()