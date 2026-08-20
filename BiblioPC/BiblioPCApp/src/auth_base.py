from abc import ABC, abstractmethod
from typing import Tuple, Optional

class BaseAuthModule(ABC):
    """
    Abstrakte Basisklasse. Jedes neue Authentifizierungs-Modul 
    MUSS diese Klasse erben und ihre Methoden implementieren.
    """

    @abstractmethod
    async def authenticate_user(self, bn: str, pw: str) -> Tuple[bool, Optional[str]]:
        """
        Prüft Benutzername und Passwort.
        Gibt (True, token_oder_id) bei Erfolg zurück, sonst (False, None).
        """
        pass

    @abstractmethod
    async def check_borrower_status(self, bn: str, token: Optional[str]) -> Optional[int]:
        """
        Prüft, ob der Benutzer gesperrt ist.
        Gibt 0 zurück, wenn ALLES OK ist. Jeder Wert > 0 bedeutet gesperrt.
        """
        pass
