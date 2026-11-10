from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', case_sensitive=False)
    app_env: str = 'development'
    database_url: str = 'sqlite:///./store-dev.db'
    cors_origins: str = 'http://localhost:5173,http://localhost:5174'
    cookie_secure: bool = False
    session_days: int = 7
    digital_code_key: str = ''
    digital_code_hmac_key: str = ''
    store_domain: str = 'http://localhost:5173'
    trust_proxy: bool = False

    @property
    def origins(self) -> list[str]:
        return [s.strip().rstrip('/') for s in self.cors_origins.split(',') if s.strip()]

    @model_validator(mode='after')
    def ensure_safe_production(self):
        if self.app_env == 'production':
            if not self.database_url.startswith('postgresql+psycopg://'):
                raise ValueError('Production requires PostgreSQL + psycopg')
            if not self.cookie_secure:
                raise ValueError('Production requires COOKIE_SECURE=true')
            if not self.digital_code_key:
                raise ValueError('Production requires DIGITAL_CODE_KEY')
            if len(self.digital_code_hmac_key) < 32:
                raise ValueError('Production requires a random DIGITAL_CODE_HMAC_KEY (at least 32 characters)')
            if any(origin.startswith('http://') for origin in self.origins):
                raise ValueError('Production CORS_ORIGINS must be HTTPS')
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
