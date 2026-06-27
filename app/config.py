"""Ortam degiskenlerinden uygulama ayarlarini yukler."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """`.env` dosyasindan / ortam degiskenlerinden okunan ayarlar."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Veritabani baglantisi (pyodbc) ---
    canias_db_driver: str = "ODBC Driver 18 for SQL Server"
    canias_db_server: str = r"DEBAKNETSIS\DB20"
    canias_db_name: str = "DBKBGYS"
    canias_db_user: str = "sa"
    canias_db_password: str = ""
    canias_db_trust_cert: str = "yes"
    canias_db_encrypt: str = "no"

    # --- CANIAS mantik sabitleri ---
    canias_client: str = "00"
    canias_langu: str = "T"
    canias_default_company: str = "01"
    canias_default_plant: str = "01"
    canias_sendika: int = 0

    # --- Uygulama ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    # main dalindaki alan adlariyla uyumluluk
    @property
    def canias_company(self) -> str:
        return self.canias_default_company

    @property
    def canias_language(self) -> str:
        return self.canias_langu

    def odbc_connection_string(self) -> str:
        """pyodbc icin ODBC baglanti dizesini olusturur."""
        return (
            f"DRIVER={{{self.canias_db_driver}}};"
            f"SERVER={self.canias_db_server};"
            f"DATABASE={self.canias_db_name};"
            f"UID={self.canias_db_user};"
            f"PWD={self.canias_db_password};"
            f"TrustServerCertificate={self.canias_db_trust_cert};"
            f"Encrypt={self.canias_db_encrypt};"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
