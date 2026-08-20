from typing import Any 
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    
    # App-Einstellungen (mit Standardwerten, falls in .env nicht gesetzt)
    interval_min: int = 1
    deny_multi_login: int = 1
    acc_z: int = 0
    secret_key: str = "S1ch3r3r_schlu3ss3l_Fu3r_die_b1bl1oth3k_die"
    admin_user: str = "useradmin"
    admin_password: str = "@ChangeMe@"
    standard_max: int = 120  # Fallback auf 2 Stunden
    auth_method: str = "gbv"
    paia_base_url: str = "https://paia.gbv.de/<ISIL>"
    # Verhalten, wenn das PAIA/GBV-Backend nicht erreichbar ist:
    # True = "fail-open" (bei Backend-Fehlern Logins erlauben),
    # False = "fail-closed" (bei Backend-Fehlern Logins ablehnen)
    paia_fail_open: bool = True
    
    # Pydantic sagen, dass es auch Umgebungsvariablen (Großbuchstaben) lesen soll
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Typ auf Any, damit das Einlesen aus der .env nicht blockiert
    allowed_status_codes: Any = {0}

    @field_validator("allowed_status_codes", mode="before")
    @classmethod
    def parse_status_codes(cls, v):
        # Falls die .env-Variable als String reinkommt (z.B. "0,1,4")
        if isinstance(v, str):
            try:
                return {int(code.strip()) for code in v.split(",") if code.strip()}
            except ValueError:
                # Falls jemand Quatsch in die .env schreibt (z.B. "null"), Fallback auf {0}
                logger.exception("Failed to parse allowed_status_codes from env: %s", v)
                return {0}
        # Falls es bereits eine Kollektion/Set ist (z.B. durch Pydantic-Defaults)
        if isinstance(v, (set, list, tuple)):
            return {int(x) for x in v}
        return {0}

settings = Settings()