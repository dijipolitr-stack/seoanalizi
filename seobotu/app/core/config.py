import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "SEO Audit Bot"
    API_V1_STR: str = "/api/v1"
    
    # DataForSEO
    DATAFORSEO_LOGIN: str = os.getenv("DATAFORSEO_LOGIN", "mock_login")
    DATAFORSEO_PASSWORD: str = os.getenv("DATAFORSEO_PASSWORD", "mock_password")
    
    # AI (OpenAI)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "mock_api_key")
    
    # Redis/Celery
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
