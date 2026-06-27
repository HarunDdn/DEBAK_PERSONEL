"""Ortam degiskenlerinden uygulama ayarlarini yukler."""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """`.env` dosyasindan / ortam degiskenlerinden okunan ayarlar."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Veritabani baglantisi (pyodbc) ---
    canias_db_driver: str = "ODBC Driver 18 for SQL Server"
    canias_db_server: str = r"DEBAKNETSIS\DB20"
    canias_db_name: str = "DEBAK803"
    canias_db_user: str = "sa"
    canias_db_password: str = "mtr+-60891011"
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

    def _available_odbc_drivers(self) -> list[str]:
        """Sistemde kurulu ODBC suruculerini dondurur."""
        import pyodbc

        return list(pyodbc.drivers())

    def _select_odbc_driver(self, candidates: Iterable[str]) -> str:
        """Kurulu ise ilk uygun SQL Server surucusunu sec.

        Bu, .env icindeki varsayilan surucu kurulu degilse IM002 hatasini
        engeller ve ortamda mevcut olan en yakin uyumlu surucuyu kullanir.
        """
        available = self._available_odbc_drivers()
        for driver in candidates:
            if driver and driver in available:
                return driver
        if self.canias_db_driver in available:
            return self.canias_db_driver
        return self.canias_db_driver

    def odbc_connection_string(self) -> str:
        """pyodbc icin ODBC baglanti dizesini olusturur."""
        driver = self._select_odbc_driver(
            (
                self.canias_db_driver,
                "ODBC Driver 18 for SQL Server",
                "ODBC Driver 17 for SQL Server",
                "SQL Server Native Client 11.0",
                "SQL Server",
            )
        )
        return (
            f"DRIVER={{{driver}}};"
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
