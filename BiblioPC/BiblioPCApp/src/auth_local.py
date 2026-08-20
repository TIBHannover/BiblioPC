from typing import Tuple, Optional
from auth_base import BaseAuthModule
# Hier könnte man die SQLAlchemy-Datenbank einbinden

class LocalAuthModule(BaseAuthModule):
    async def authenticate_user(self, bn: str, pw: str) -> Tuple[bool, Optional[str]]:
        # Beispiel-Logik: Prüfe gegen lokale 'benutzer' Tabelle
        # Wenn Passwort stimmt, gib True und als "Token" einfach 'lokal' zurück
        if bn == "99999999" and pw == "testpw123":
            return True, "lokaler_token_id"
        return False, None

    async def check_borrower_status(self, bn: str, token: Optional[str]) -> Optional[int]:
        # Lokale Nutzer sind standardmäßig nie gesperrt (0 = Alles OK)
        return 0
