import pytest
from app.core.config import Settings

def test_settings_load():
    settings = Settings()
    assert settings.PROJECT_NAME == "AI Document Formatting Platform"
    assert settings.MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024
