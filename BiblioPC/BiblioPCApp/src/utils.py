import re
from datetime import datetime, timedelta
import logging
from typing import Optional

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from models import BenutzerMax, Zeitlimit

def is_ben_nr_plausibel(bn: str) -> bool:
    """Prüft, ob die Benutzernummer 8 bis 11 Ziffern lang ist und optional mit 'x' endet."""
    return bool(re.match(r"^\d{8,11}[xX]?$", bn))

def get_ende_acc_z() -> str:
    """Bestimmt das Enddatum (YYYYMMDD) basierend auf settings.acc_z (0=Tag, 1=Woche, 2=Monat)."""
    heute = datetime.now()
    
    if settings.acc_z == 0:
        return heute.strftime("%Y%m%d")
    elif settings.acc_z == 1:
        tage_bis_sonntag = 6 - heute.weekday()
        return (heute + timedelta(days=tage_bis_sonntag)).strftime("%Y%m%d")
    elif settings.acc_z == 2:
        if heute.month == 12:
            naechster_monat = heute.replace(year=heute.year + 1, month=1, day=1)
        else:
            naechster_monat = heute.replace(month=heute.month + 1, day=1)
        return (naechster_monat - timedelta(days=1)).strftime("%Y%m%d")
    return heute.strftime("%Y%m%d")

def parse_time_str_to_minutes(time_str: str) -> Optional[int]:
    """Wandelt 'HH:MM:SS' oder 'HH:MM' in Minuten um.

    Liefert `None` bei ungültigem Format.
    """
    if not time_str or not isinstance(time_str, str):
        logger.warning("parse_time_str_to_minutes: empty or non-string time_str=%r", time_str)
        return None

    # Akzeptiertes Format: H{1,3}:MM(:SS)? wobei MM und SS 00-59 sind
    m = re.match(r"^(\d{1,3}):([0-5][0-9])(?::([0-5][0-9]))?$", time_str)
    if not m:
        logger.warning("parse_time_str_to_minutes: invalid format time_str=%s", time_str)
        return None

    try:
        stunden = int(m.group(1))
        minuten = int(m.group(2))
        return stunden * 60 + minuten
    except Exception:
        logger.exception("parse_time_str_to_minutes: failed to convert parts for time_str=%s", time_str)
        return None

async def get_user_max_minutes(bn: str, db: AsyncSession) -> int:
    """
    Ermittelt das maximale Zeitguthaben für einen Benutzer in Minuten.
    Entspricht der alten Logik aus getstdmax.php (inklusive Wildcards und globalem Standard).
    """
    heute = datetime.now().date()
    
    # 1. Spezifischen, exakten Eintrag für die BN suchen
    query_exact = select(BenutzerMax.Max).where(
        BenutzerMax.BenNr == bn,
        BenutzerMax.Von <= heute,
        BenutzerMax.Bis >= heute
    )
    res = await db.execute(query_exact)
    exact_max = res.scalar_one_or_none()
    
    if exact_max:
        val = parse_time_str_to_minutes(exact_max)
        if val is not None:
            return val
        logger.warning("get_user_max_minutes: exact Zeitlimit %r has invalid format for bn=%s", exact_max, bn)
        
    # 2. Wildcard-Einträge suchen (die auf '*' enden)
    query_wildcards = select(BenutzerMax.BenNr, BenutzerMax.Max).where(
        BenutzerMax.BenNr.like("%*"),
        BenutzerMax.Von <= heute,
        BenutzerMax.Bis >= heute
    )
    res_wildcards = await db.execute(query_wildcards)
    wildcards = res_wildcards.all()
    
    best_match_len = -1
    chosen_max_str = None
    
    for row_bn, row_max in wildcards:
        prefix = row_bn.rstrip("*")
        if bn.startswith(prefix):
            # Je länger das gefundene Pattern, desto spezifischer das Limit (wie im PHP)
            if len(row_bn) > best_match_len:
                best_match_len = len(row_bn)
                chosen_max_str = row_max
                
    if chosen_max_str:
        val = parse_time_str_to_minutes(chosen_max_str)
        if val is not None:
            return val
        logger.warning("get_user_max_minutes: wildcard Zeitlimit %r has invalid format for bn=%s", chosen_max_str, bn)
        
    # 3. Globalen Standardwert aus 'zeitlimit' laden
    query_default = select(Zeitlimit.StandardMax)
    res_default = await db.execute(query_default)
    default_max = res_default.scalar_one_or_none()
    
    if default_max:
        val = parse_time_str_to_minutes(default_max)
        if val is not None:
            return val
        logger.warning("get_user_max_minutes: default Zeitlimit %r has invalid format", default_max)
        
    # Absoluter Notfall-Fallback, falls die DB komplett leer ist
    return 120


def is_valid_ip(ip_str: str) -> bool:
    """Prüft, ob eine Zeichenkette eine gültige IPv4- oder IPv6-Adresse darstellt."""
    if not ip_str or not isinstance(ip_str, str):
        return False
    try:
        import ipaddress
        ipaddress.ip_address(ip_str)
        return True
    except Exception:
        logger.debug("is_valid_ip: invalid ip=%r", ip_str)
        return False
