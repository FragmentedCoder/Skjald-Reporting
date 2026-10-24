from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment (see deploy/.env.example)."""

    model_config = SettingsConfigDict(env_prefix="SKJALD_")

    data_dir: str = "/data"
    master_key_path: str = "/etc/skjald/master.key"


settings = Settings()
