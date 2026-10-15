from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "AI Document Formatting Platform"
    DATABASE_URL: str = "sqlite:///./test.db"
    STORAGE_PATH: str = "/tmp/formatto"
    LLM_API_KEY_PLACEHOLDER: str = ""
    MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10MB
    SUPPORTED_FILE_TYPES: list[str] = ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["*"]

settings = Settings()
