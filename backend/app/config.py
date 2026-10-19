from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    mongo_uri: str = 'mongodb://127.0.0.1:27017'
    mongo_database: str = 'fieldnote'
    app_env: Literal['development', 'test', 'production'] = 'development'
    public_origin: str = 'http://localhost:5173'
    session_hours: int = 8

    @model_validator(mode='after')
    def validate_production_origin(self):
        if self.production:
            origin = urlsplit(self.public_origin)
            if origin.scheme != 'https' or not origin.hostname or origin.path not in ('', '/') or origin.query or origin.fragment or origin.username:
                raise ValueError('Production PUBLIC_ORIGIN must be a single HTTPS origin, without a path or credentials.')
        return self

    @property
    def production(self) -> bool:
        return self.app_env == 'production'

    @property
    def cookie_name(self) -> str:
        return '__Host-fieldnote' if self.production else 'fieldnote_session'

    @property
    def allowed_origins(self) -> set[str]:
        if self.production:
            return {self.public_origin.rstrip('/')}
        return {self.public_origin.rstrip('/'), 'http://localhost:5173',
                'http://127.0.0.1:5173', 'http://localhost:8000', 'http://127.0.0.1:8000'}

