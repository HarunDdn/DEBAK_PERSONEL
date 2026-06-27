from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_driver: str = "mssql"
    db_host: str = "localhost"
    db_port: int = 1433
    db_name: str = "CANIAS"
    db_user: str = ""
    db_password: str = ""

    canias_client: str = "00"
    canias_company: str = "01"
    canias_language: str = "T"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    @property
    def database_url(self) -> str:
        if self.db_driver == "oracle":
            return (
                f"oracle+oracledb://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/?service_name={self.db_name}"
            )
        return (
            f"mssql+pyodbc://{self.db_user}:{self.db_password}"
            f"@{self.db_host},{self.db_port}/{self.db_name}"
            "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
