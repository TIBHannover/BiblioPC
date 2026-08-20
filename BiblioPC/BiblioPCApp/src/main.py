from fastapi import FastAPI, Depends, Request, Form, responses, status
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, distinct
from datetime import datetime, timedelta
from database import get_db, engine, async_session
from models import Base, Aktiv, LogData, LokalerBenutzer, Nutzung, Zeitlimit, Bearbeiter, Sperrung, BenutzerMax, Zugang
from utils import is_ben_nr_plausibel, get_user_max_minutes, get_ende_acc_z, parse_time_str_to_minutes
from utils import is_valid_ip
from config import settings
from auth_gbv import GBVAuthModule
from auth_local import LocalAuthModule
import bcrypt
import logging
import os

app = FastAPI(title="Bibliothek PC Login API & Weboberfläche")

# Logging konfigurieren
log_file = os.path.join(os.path.dirname(__file__), "bibliopc.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8")
    ]
)
# Suppress verbose watchfiles log messages during development
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logger = logging.getLogger("bibliopc")

# =====================================================================
# SITZUNGSMANAGEMENT, TEMPLATE-ENGINE, PASSWORT-HASHING
# =====================================================================

from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware, 
    secret_key=settings.secret_key, 
    session_cookie="bibliopc_session",
    same_site="lax",
    https_only=False # Auf True setzen, sobald HTTPS produktiv im Nginx-Proxy erzwungen wird
)

# Statische CSS-Dateien und Jinja2 HTML-Templates registrieren
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Custom Jinja2 Filter für deutsches Datumsformat
def datetime_de_filter(value):
    if not value:
        return ""
    # Falls es ein datetime-Objekt ist (SQLAlchemy standard)
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y %H:%M:%S")
    # Falls es als String aus der SQLite kommt
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(value).replace(" ", "T"))
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception as e:
        logger.exception("datetime_de_filter: failed to parse date value=%s", value)
        return str(value)

# Den Filter bei Jinja2 anmelden
templates.env.filters["datetime_de"] = datetime_de_filter

# Hilfsklasse für Passwort-Hashing und -Verifizierung
class NativeBcryptContext:
    def hash(self, secret: str) -> str:
        # Erzeugt einen Bcrypt-Hash mit einem zufälligen Salt und 12 Runden
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(secret.encode('utf-8'), salt).decode('utf-8')

    def verify(self, secret: str, hash: str) -> bool:
        try:
            return bcrypt.checkpw(secret.encode('utf-8'), hash.encode('utf-8'))
        except Exception as e:
            logger.exception("Password verification failed")
            return False

pwd_context = NativeBcryptContext()

@app.on_event("startup")
async def startup():
    """ Erstellt alle Tabellen in der SQLite-Datei, falls sie noch nicht da sind und initialisiert das StandardMax aus der .env-Datei."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    stunden = settings.standard_max // 60
    minuten = settings.standard_max % 60
    standard_max_str = f"{stunden:02d}:{minuten:02d}:00"

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(select(Zeitlimit))
            db_zeitlimit = result.scalars().first()
            
            if not db_zeitlimit:
                neue_zeitlimit = Zeitlimit(StandardMax=standard_max_str)
                session.add(neue_zeitlimit)
            else:
                if db_zeitlimit.StandardMax != standard_max_str:
                    from sqlalchemy import delete
                    await session.execute(delete(Zeitlimit))
                    neue_zeitlimit = Zeitlimit(StandardMax=standard_max_str)
                    session.add(neue_zeitlimit)

            admin_query = select(Bearbeiter).where(Bearbeiter.Bearb == settings.admin_user)
            admin_result = await session.execute(admin_query)
            db_admin = admin_result.scalar_one_or_none()
            
            if not db_admin:
                hashed_password = pwd_context.hash(settings.admin_password)

                neuer_admin = Bearbeiter(
                    Bearb=settings.admin_user, 
                    Passwort=hashed_password
                )
                session.add(neuer_admin)

# Fabrik-Muster (Factory), um das richtige Modul zu wählen
if settings.auth_method == "gbv":
    auth_service = GBVAuthModule()
elif settings.auth_method == "local":
    auth_service = LocalAuthModule()
else:
    raise ValueError(f"Unbekannte Authentifizierungsmethode: {settings.auth_method}")


# =====================================================================
# WEB-INTERFACE (Login-Seite, Übersicht, Logout)
# =====================================================================

@app.get("/", response_class=responses.HTMLResponse)
async def login_page(request: Request):
    """Zeigt die Loginmaske an. Leitet weiter, falls eingeloggt."""
    if request.session.get("userid"):
        return responses.RedirectResponse(url="/uebersicht", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html")


@app.post("/login")
async def do_login(
    request: Request, 
    bn: str = Form(...), 
    pw: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    # 1. Bearbeiter aus SQLite laden
    query = select(Bearbeiter).where(Bearbeiter.Bearb == bn)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    # 2. Passwort mit dem gespeicherten Hash verifizieren
    if user and pwd_context.verify(pw, user.Passwort):
        request.session["userid"] = user.id
        return responses.RedirectResponse(url="/uebersicht", status_code=status.HTTP_303_SEE_OTHER)
    
    # Fehlerfall: Template mit Fehlermeldung neu rendern
    return templates.TemplateResponse(
        request,
        "login.html",
        context={"error_message": "Benutzername oder Passwort ungültig!"}
    )

@app.get("/uebersicht", response_class=responses.HTMLResponse)
async def uebersicht_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Zeigt die Liste aller aktiven PCs an."""
    # Schutzprüfung: Wenn nicht eingeloggt -> Zurück zum Login
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Aktive Nutzer sortiert nach Login-Zeitpunkt laden
    query = select(Aktiv).order_by(Aktiv.Login.desc())
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Datum für die Überschrift formatieren (z.B. "20.05.2026 - 14:30")
    datum_str = datetime.now().strftime("%d.%m.%Y - %H:%M")
    
    return templates.TemplateResponse(
        request, 
        "benutzeruebersicht.html", 
        context={"users": users, "datum": datum_str}
    )

@app.get("/passwort-aendern", response_class=responses.HTMLResponse)
async def passwort_aendern_page(request: Request):
    # Sicherheits-Check: Nur eingeloggte Bearbeiter dürfen hierhin
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(request, "passwort_aendern.html")

@app.post("/passwort-aendern")
async def do_passwort_aendern(
    request: Request, 
    alt_pw: str = Form(...), 
    neu_pw: str = Form(...), 
    neu_pw_wdh: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    # 1. Sicherheits-Check
    user_id = request.session.get("userid")
    if not user_id:
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # 2. Den aktuellen Bearbeiter aus der DB laden
    query = select(Bearbeiter).where(Bearbeiter.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Validierung: Altes Passwort korrekt?
    if not pwd_context.verify(alt_pw, user.Passwort):
        return templates.TemplateResponse(
            request, "passwort_aendern.html", 
            context={"error_message": "Das aktuelle Passwort ist nicht korrekt!"}
        )
        
    # 4. Validierung: Stimmen die neuen Passwörter überein?
    if neu_pw != neu_pw_wdh:
        return templates.TemplateResponse(
            request, "passwort_aendern.html", 
            context={"error_message": "Die neuen Passwörter stimmen nicht überein!"}
        )

    # 5. Alles okay -> Passwort neu hashen und speichern
    user.Passwort = pwd_context.hash(neu_pw)
    await db.commit()

    return templates.TemplateResponse(
        request, "passwort_aendern.html", 
        context={"success_message": "Dein Passwort wurde erfolgreich geändert!"}
    )

@app.get("/benutzer/loeschen/{ben_nr}")
async def delete_user(request: Request, ben_nr: str, db: AsyncSession = Depends(get_db)):
    """Löscht ein hängengebliebene Anmeldung aus der 'aktiv'-Tabelle."""
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Aus DB entfernen
    await db.execute(delete(Aktiv).where(Aktiv.BenNr == ben_nr))
    await db.commit()
    
    return responses.RedirectResponse(url="/uebersicht", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/benutzerverwaltung", response_class=responses.HTMLResponse)
async def benutzerverwaltung_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Sortierung nach echten Erstellungsdatum (neueste zuerst)
    query = select(LokalerBenutzer).order_by(LokalerBenutzer.Datum.desc())
    result = await db.execute(query)
    local_users = result.scalars().all()
    
    return templates.TemplateResponse(
        request, 
        "benutzerverwaltung.html", 
        context={"local_users": local_users}
    )

@app.post("/benutzerverwaltung")
async def do_add_local_user(
    request: Request,
    ben_nr: str = Form(...),
    pw: str = Form(...),
    von: str = Form(...),
    bis: str = Form(...),
    bemerkungen: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Überprüfen, ob die Benutzernummer bereits existiert
    check_query = select(LokalerBenutzer).where(LokalerBenutzer.BenNr == ben_nr.strip())
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        query = select(LokalerBenutzer).order_by(LokalerBenutzer.Datum.desc())
        res = await db.execute(query)
        local_users = res.scalars().all()
        return templates.TemplateResponse(
            request, "benutzerverwaltung.html",
            context={
                "local_users": local_users,
                "error_message": "Die Benutzernummer ist bereits vergeben. Bitte wählen Sie eine andere."
            }
        )

    # 2. Namen des angemeldeten Bearbeiters holen
    user_id = request.session.get("userid")
    bearb_query = select(Bearbeiter.Bearb).where(Bearbeiter.id == user_id)
    bearb_result = await db.execute(bearb_query)
    current_bearb = bearb_result.scalar_one_or_none() or "System"

    # 3. Datumsstrings in reine Python-'date'-Objekte konvertieren
    try:
        dt_von = datetime.strptime(von.split(" ")[0], "%Y-%m-%d").date()
        dt_bis = datetime.strptime(bis.split(" ")[0], "%Y-%m-%d").date()
    except Exception as e:
        logger.exception("Failed to parse 'von'/'bis' for LokalerBenutzer: von=%s bis=%s", von, bis)
        dt_von = datetime.now().date()
        dt_bis = datetime.now().date()

    # 4. Eintrag mit ALLEN neuen Spalten in die Datenbank schreiben
    neuer_user = LokalerBenutzer(
        BenNr=ben_nr.strip(),
        Pw=pw.strip(),
        Von=dt_von,
        Bis=dt_bis,
        Bearb=current_bearb,
        Bemerkungen=bemerkungen.strip() if bemerkungen else None,
        Host="WebInterface"  # Markierung, dass es über die Admin-Oberfläche kam
    )
    
    db.add(neuer_user)
    await db.commit()

    query = select(LokalerBenutzer).order_by(LokalerBenutzer.Datum.desc())
    res = await db.execute(query)
    local_users = res.scalars().all()

    return templates.TemplateResponse(
        request, "benutzerverwaltung.html",
        context={
            "local_users": local_users,
            "success_message": f"Lokaler Benutzer {ben_nr.strip()} angelegt. Passwort: {pw}"
        }
    )

@app.get("/benutzerverwaltung/loeschen/{ben_nr}")
async def delete_local_user(request: Request, ben_nr: str, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    query = select(LokalerBenutzer).where(LokalerBenutzer.BenNr == ben_nr)
    result = await db.execute(query)
    user_to_delete = result.scalar_one_or_none()
    
    if user_to_delete:
        await db.delete(user_to_delete)
        await db.commit()
        
    return responses.RedirectResponse(url="/benutzerverwaltung", status_code=status.HTTP_303_SEE_OTHER)

# =====================================================================
# BEARBEITERVERWALTUNG (Hinzufügen und Löschen von Admins/Mitarbeitern)
# =====================================================================

@app.get("/bearbeiterverwaltung", response_class=responses.HTMLResponse)
async def bearbeiterverwaltung_page(request: Request, db: AsyncSession = Depends(get_db)):
    # Sicherheits-Check: Nur eingeloggt zugänglich
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Alle registrierten Bearbeiter alphabetisch sortiert abrufen
    query = select(Bearbeiter).order_by(Bearbeiter.Bearb.asc())
    result = await db.execute(query)
    bearbeiter_liste = result.scalars().all()
    
    return templates.TemplateResponse(
        request, 
        "bearbeiterverwaltung.html", 
        context={"bearbeiter_liste": bearbeiter_liste}
    )


@app.post("/bearbeiterverwaltung")
async def do_add_bearbeiter(
    request: Request,
    bearb_name: str = Form(...),
    passwort: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    bearb_name_clean = bearb_name.strip()

    # 1. Überprüfen, ob der Name bereits vergeben ist
    check_query = select(Bearbeiter).where(Bearbeiter.Bearb == bearb_name_clean)
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        res = await db.execute(select(Bearbeiter).order_by(Bearbeiter.Bearb.asc()))
        bearbeiter_liste = res.scalars().all()
        return templates.TemplateResponse(
            request, "bearbeiterverwaltung.html",
            context={
                "bearbeiter_liste": bearbeiter_liste,
                "error_message": f"Der Bearbeiter '{bearb_name_clean}' existiert bereits!"
            }
        )

    # 2. Passwort mit bcrypt hashen
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(passwort.encode('utf-8'), salt).decode('utf-8')

    # 3. In die Datenbank eintragen
    neuer_bearbeiter = Bearbeiter(
        Bearb=bearb_name_clean,
        Passwort=hashed_password
    )
    db.add(neuer_bearbeiter)
    await db.commit()

    # Aktualisierte Liste für die Ansicht holen
    res = await db.execute(select(Bearbeiter).order_by(Bearbeiter.Bearb.asc()))
    bearbeiter_liste = res.scalars().all()

    return templates.TemplateResponse(
        request, "bearbeiterverwaltung.html",
        context={
            "bearbeiter_liste": bearbeiter_liste,
            "success_message": f"Bearbeiter '{bearb_name_clean}' wurde erfolgreich angelegt."
        }
    )

@app.get("/bearbeiterverwaltung/loeschen/{bearb_id}")
async def delete_bearbeiter(request: Request, bearb_id: int, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    # Bearbeiter anhand der ID suchen
    query = select(Bearbeiter).where(Bearbeiter.id == bearb_id)
    result = await db.execute(query)
    user_to_delete = result.scalar_one_or_none()
    
    if user_to_delete:
        # 'useradmin' darf unter keinen Umständen gelöscht werden
        if user_to_delete.Bearb == "useradmin":
            return responses.RedirectResponse(url="/bearbeiterverwaltung", status_code=status.HTTP_303_SEE_OTHER)
            
        await db.delete(user_to_delete)
        await db.commit()
        
    return responses.RedirectResponse(url="/bearbeiterverwaltung", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/benutzersperren", response_class=responses.HTMLResponse)
async def benutzersperren_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Alle Sperren abrufen (neueste zuerst)
    query = select(Sperrung).order_by(Sperrung.Datum.desc())
    result = await db.execute(query)
    blocked_users = result.scalars().all()
    
    return templates.TemplateResponse(
        request, 
        "benutzersperren.html", 
        context={"blocked_users": blocked_users}
    )

@app.post("/benutzersperren")
async def do_add_sperrung(
    request: Request,
    ben_nr: str = Form(...),
    von: str = Form(...),
    bis: str = Form(...),
    bemerkungen: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Prüfen, ob für diese Nummer bereits eine Sperre existiert
    check_query = select(Sperrung).where(Sperrung.BenNr == ben_nr.strip())
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        query = select(Sperrung).order_by(Sperrung.Datum.desc())
        res = await db.execute(query)
        blocked_users = res.scalars().all()
        return templates.TemplateResponse(
            request, "benutzersperren.html",
            context={
                "blocked_users": blocked_users,
                "error_message": "Für diese Benutzernummer existiert bereits ein Sperreintrag."
            }
        )

    # 2. Bearbeiter-Kürzel ermitteln
    user_id = request.session.get("userid")
    bearb_query = select(Bearbeiter.Bearb).where(Bearbeiter.id == user_id)
    bearb_result = await db.execute(bearb_query)
    current_bearb = bearb_result.scalar_one_or_none() or "System"

    # 3. Datumsstrings in reine Python-Dates konvertieren (für Column(Date))
    try:
        dt_von = datetime.strptime(von, "%Y-%m-%d").date()
        dt_bis = datetime.strptime(bis, "%Y-%m-%d").date()
    except Exception as e:
        logger.exception("Failed to parse 'von'/'bis' for Sperrung: von=%s bis=%s", von, bis)
        dt_von = datetime.now().date()
        dt_bis = datetime.now().date()

    # 4. In die Tabelle 'sperrung' schreiben 
    neue_sperre = Sperrung(
        BenNr=ben_nr.strip(),
        gesperrt=True,
        Von=dt_von,
        Bis=dt_bis,
        Bearb=current_bearb,
        Bemerkungen=bemerkungen.strip()
    )
    
    db.add(neue_sperre)
    await db.commit()
    
    return responses.RedirectResponse(url="/benutzersperren", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/benutzersperren/loeschen/{ben_nr}")
async def delete_sperrung(request: Request, ben_nr: str, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    query = select(Sperrung).where(Sperrung.BenNr == ben_nr)
    result = await db.execute(query)
    sperre_to_delete = result.scalar_one_or_none()
    
    if sperre_to_delete:
        await db.delete(sperre_to_delete)
        await db.commit()
        
    return responses.RedirectResponse(url="/benutzersperren", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/benutzerzeitkontingent", response_class=responses.HTMLResponse)
async def zeitkontingent_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Alle benutzerdefinierten Zeitkontingente abrufen
    query = select(Zugang).order_by(Zugang.BenNr)
    result = await db.execute(query)
    kontingente = result.scalars().all()
    
    return templates.TemplateResponse(
        request, 
        "benutzerzeitkontingent.html", 
        context={"kontingente": kontingente}
    )

@app.post("/benutzerzeitkontingent")
async def do_add_zeitkontingent(
    request: Request,
    ben_nr: str = Form(...),
    max_stunden: int = Form(...),
    bemerkungen: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    bn_clean = ben_nr.strip()

    # 1. Prüfen, ob für diese Nummer bereits ein Sondereintrag aktiv ist
    check_query = select(Zugang).where(Zugang.BenNr == bn_clean)
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        res = await db.execute(select(Zugang).order_by(Zugang.BenNr))
        kontingente = res.scalars().all()
        return templates.TemplateResponse(
            request, "benutzerzeitkontingent.html",
            context={
                "kontingente": kontingente,
                "error_message": f"Für die Nummer {bn_clean} existiert bereits ein Kontingent-Eintrag."
            }
        )

    # 2. Bearbeiter-Kürzel holen
    user_id = request.session.get("userid")
    bearb_query = select(Bearbeiter.Bearb).where(Bearbeiter.id == user_id)
    bearb_result = await db.execute(bearb_query)
    current_bearb = bearb_result.scalar_one_or_none() or "System"

    # Datumsberechnungen für den Zeitraum (Aktuelle Woche bis Sonntag)
    heute = datetime.now().date()
    tage_bis_sonntag = 6 - heute.weekday()
    ende_datum = heute + timedelta(days=tage_bis_sonntag)
    
    # Format für die Tabelle 'nutzung' (YYYYMMDD)
    ende_acc_z_str = ende_datum.strftime("%Y%m%d")

    # Stunden in das Datenbank-Zeitformat konvertieren (z.B. 60 -> "60:00:00")
    max_zeit_str = f"{max_stunden:02d}:00:00"
    used_zeit_str = "00:00:00"

    try:
        # -----------------------------------------------------------------
        # SCHRITT A: In die Tabelle 'zugang' schreiben (Für die Admin-Übersicht)
        # -----------------------------------------------------------------
        neues_kontingent = Zugang(
            BenNr=bn_clean,
            Von=heute,
            Bis=ende_datum,
            Max=max_zeit_str,
            Used=used_zeit_str,
            Bearb=current_bearb,
            Bemerkungen=bemerkungen.strip() if bemerkungen else ""
        )
        db.add(neues_kontingent)

        # -----------------------------------------------------------------
        # SCHRITT B: In die Tabelle 'benutzermax' schreiben (Für get_user_max_minutes)
        # -----------------------------------------------------------------
        # Falls ein alter Eintrag für den User existiert, vorsichtshalber löschen
        await db.execute(delete(BenutzerMax).where(BenutzerMax.BenNr == bn_clean))
        
        neuer_benutzer_max = BenutzerMax(
            BenNr=bn_clean,
            Max=max_zeit_str,
            Von=heute,
            Bis=ende_datum
        )
        db.add(neuer_benutzer_max)

        # -----------------------------------------------------------------
        # SCHRITT C: In die Tabelle 'nutzung' schreiben oder updaten
        # -----------------------------------------------------------------
        nutzung_query = select(Nutzung).where(Nutzung.BenNr == bn_clean, Nutzung.Bis == ende_acc_z_str)
        nutzung_res = await db.execute(nutzung_query)
        nutzung_eintrag = nutzung_res.scalar_one_or_none()

        if nutzung_eintrag:
            # Eintrag für laufende Woche existiert bereits -> Max-Limit hochsetzen
            nutzung_eintrag.Max = max_zeit_str
        else:
            # Es gab diese Woche noch keinen Login -> Neuen Zeiteintrag anlegen
            neue_nutzung = Nutzung(
                BenNr=bn_clean,
                Max=max_zeit_str,
                Used=used_zeit_str,
                Bis=ende_acc_z_str
            )
            db.add(neue_nutzung)

        # Alles zusammen sicher in einer Transaktion speichern
        await db.commit()

    except Exception as e:
        logger.exception("Fehler beim Erstellen des Zeitkontingents für %s", bn_clean)
        await db.rollback()
        # Hier optional eine Fehlermeldung an das Template übergeben

    return responses.RedirectResponse(url="/benutzerzeitkontingent", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/benutzerzeitkontingent/loeschen/{ben_nr}")
async def delete_zeitkontingent(request: Request, ben_nr: str, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    bn_clean = ben_nr.strip()
    
    # Aus 'zugang' löschen
    await db.execute(delete(Zugang).where(Zugang.BenNr == bn_clean))
    # Aus 'benutzermax' löschen
    await db.execute(delete(BenutzerMax).where(BenutzerMax.BenNr == bn_clean))
    
    # Hinweis: Aus 'nutzung' löschen wir es meistens nicht, da dort die real verbrauchten 
    # Minuten stehen. Wenn du das Limit der laufenden Woche auf Standard (z.B. 14:00:00) 
    # zurücksetzen willst, kannst du das hier optional tun.

    await db.commit()
    return responses.RedirectResponse(url="/benutzerzeitkontingent", status_code=status.HTTP_303_SEE_OTHER)

def berechne_restzeit(max_str: str, used_str: str) -> str:
    # Nutze parse_time_str_to_minutes für konsistente Validierung
    max_minuten = parse_time_str_to_minutes(max_str)
    used_minuten = parse_time_str_to_minutes(used_str)

    if max_minuten is None or used_minuten is None:
        logger.warning("berechne_restzeit: invalid time format max=%r used=%r", max_str, used_str)
        return "00:00 Std."

    rest_minuten = max_minuten - used_minuten
    if rest_minuten <= 0:
        return "00:00 Std."

    stunden = rest_minuten // 60
    minuten = rest_minuten % 60
    return f"{stunden:02d}:{minuten:02d} Std."

@app.get("/benutzerstatistik", response_class=responses.HTMLResponse)
async def statistik_page_get(request: Request):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Standardmäßig das heutige Datum im Format YYYY-MM-DD für Flatpickr mitgeben
    heute_str = datetime.now().strftime("%Y-%m-%d")
    
    return templates.TemplateResponse(
        request, 
        "benutzerstatistik.html", 
        context={
            "ben_nr": None,
            "selected_date": heute_str
        }
    )


@app.post("/benutzerstatistik", response_class=responses.HTMLResponse)
async def statistik_page_post(
    request: Request, 
    ben_nr: str = Form(...), 
    ausgewaehltes_datum: str = Form(...),  # Das neue empfangene Datumsfeld
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    search_bn = ben_nr.strip()
    if not search_bn:
        return templates.TemplateResponse(request, "benutzerstatistik.html", context={"error_message": "Bitte eine Nummer eingeben."})

    # Parsen des gewählten Datums
    try:
        filter_datum = datetime.strptime(ausgewaehltes_datum, "%Y-%m-%d").date()
    except ValueError:
        filter_datum = datetime.now().date()

    # Formatiertes Datum für die Anzeige-Überschrift (z.B. "20.05.2026")
    am_datum_formatiert = filter_datum.strftime("%d.%m.%Y")

    # 1. Wöchentliches Fristende (Sonntag) für die Tabelle 'nutzung' berechnen
    tage_bis_sonntag = 6 - filter_datum.weekday()
    sonntag_db_format = (filter_datum + timedelta(days=tage_bis_sonntag)).strftime("%Y%m%d")

    # 2. Aktuelles Wochen-Zeitkonto für diese Nummer abrufen
    nutzung_query = select(Nutzung).where(Nutzung.BenNr == search_bn, Nutzung.Bis == sonntag_db_format)
    nutzung_result = await db.execute(nutzung_query)
    aktuelles_konto = nutzung_result.scalar_one_or_none()

    # 3. Live-Guthaben berechnen
    guthaben_formatiert = "14:00 Std."
    if aktuelles_konto:
        guthaben_formatiert = berechne_restzeit(aktuelles_konto.Max, aktuelles_konto.Used)

    # 4. Protokolle NUR des ausgewählten Tages filtern und nach Uhrzeit sortieren
    log_query = select(LogData).where(
        LogData.BenNr == search_bn,
        LogData.Datum == filter_datum
    ).order_by(LogData.Zeit.desc())
    
    log_result = await db.execute(log_query)
    log_data = log_result.scalars().all()
    
    return templates.TemplateResponse(
        request, 
        "benutzerstatistik.html", 
        context={
            "ben_nr": search_bn,
            "selected_date": ausgewaehltes_datum,
            "am_datum_formatiert": am_datum_formatiert,
            "log_data": log_data,
            "konto": aktuelles_konto,
            "guthaben": guthaben_formatiert
        }
    )

@app.get("/tagesprotokoll", response_class=responses.HTMLResponse)
async def tagesprotokoll_get(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    heute_str = datetime.now().strftime("%Y-%m-%d")
    
    # Dynamisch alle Hosts ermitteln, die überhaupt in der DB existieren
    host_query = select(distinct(LogData.Host)).where(LogData.Host.isnot(None)).order_by(LogData.Host.asc())
    host_result = await db.execute(host_query)
    hosts = host_result.scalars().all()
    
    return templates.TemplateResponse(
        request, 
        "tagesprotokoll.html", 
        context={
            "selected_date": heute_str,
            "selected_host": None,
            "hosts": hosts,
            "protokoll_data": []
        }
    )

@app.post("/tagesprotokoll", response_class=responses.HTMLResponse)
async def tagesprotokoll_post(
    request: Request,
    datum: str = Form(...),
    host: str = Form(None), # Kann beim ersten Abschicken oder Wechseln leer sein
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("userid"):
        return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        filter_datum = datetime.strptime(datum, "%Y-%m-%d").date()
    except ValueError:
        filter_datum = datetime.now().date()
        
    # 1. Dynamisch NUR die Hosts ermitteln, die AN DIESEM TAG aktiv waren
    host_query = select(distinct(LogData.Host)).where(
        LogData.Datum == filter_datum,
        LogData.Host.isnot(None)
    ).order_by(LogData.Host.asc())
    host_result = await db.execute(host_query)
    hosts = host_result.scalars().all()
    
    protokoll_data = []
    error_message = None
    
    # 2. Wenn ein Host ausgewählt wurde, die passenden Protokolle laden
    if host:
        log_query = select(LogData).where(
            LogData.Datum == filter_datum,
            LogData.Host == host
        ).order_by(LogData.Zeit.desc()) # Chronologisch von morgens nach abends
        
        log_result = await db.execute(log_query)
        protokoll_data = log_result.scalars().all()
        
        if not protokoll_data:
            error_message = f"Keine Protokolleinträge für PC '{host}' an diesem Tag vorhanden."
            
    am_datum_formatiert = filter_datum.strftime("%d.%m.%Y")
    
    return templates.TemplateResponse(
        request,
        "tagesprotokoll.html",
        context={
            "selected_date": datum,
            "selected_host": host,
            "hosts": hosts,
            "protokoll_data": protokoll_data,
            "am_datum_formatiert": am_datum_formatiert,
            "error_message": error_message
        }
    )

@app.get("/logout")
async def do_logout(request: Request):
    request.session.clear()
    return responses.RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# =====================================================================
# API-ENDPUNKTE (ILogin, ILogout, ILoginWH)
# =====================================================================

@app.post("/ilogout", response_class=PlainTextResponse)
async def ilogout(
    request: Request, 
    ip: str = Form(None),
    host: str = Form(None), 
    db: AsyncSession = Depends(get_db)
):
    """Benutzer wird anhand der Client IP abgemeldet."""
    client_ip = ip if ip else request.headers.get("x-real-ip", request.client.host if request.client else None)
    # Validate IP
    if client_ip:
        if not is_valid_ip(client_ip):
            logger.warning("ilogout: received invalid ip=%r from host=%r", client_ip, host)
            return "err"
    else:
        logger.warning("ilogout: no client IP available from request for host=%r", host)
        return "err"
    client_host = host if host else request.headers.get("host", "unknown")

    try:
        query = select(Aktiv.BenNr).where(Aktiv.IP == client_ip)
        result = await db.execute(query)
        bn = result.scalar_one_or_none()

        if bn:
            await db.execute(delete(Aktiv).where(Aktiv.IP == client_ip))
            await _write_log(db, "O", bn, client_ip, client_host)
            await db.commit()
            return "ok"
        return "not_active"
    except Exception as e:
        logger.exception("Error in ilogout for ip=%s host=%s", client_ip, client_host)
        await db.rollback()
        return "err"


@app.post("/ilogin", response_class=PlainTextResponse)
async def ilogin(
    request: Request,
    bn: str = Form(...),
    pw: str = Form(...),
    ip: str = Form(None),   
    host: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Benutzer meldet sich an."""
    # Priorisiere die übergebenen Form-Daten, nutze die Header als Fallback
    client_ip = ip if ip else request.headers.get("x-real-ip", request.client.host if request.client else "0.0.0.0")
    client_host = host if host else request.headers.get("host", "unknown")

    if not is_ben_nr_plausibel(bn):
        logger.warning("ilogin: invalid ben_nr received: %r", bn)
        return "err"

    try:
        heute = datetime.now().date()

        # Prüfe ob der Benutzer gesperrt ist (Sperrung existiert und aktuelles Datum liegt im Sperrzeitraum)
        sperr_query = select(Sperrung).where(Sperrung.BenNr == bn.strip())
        sperr_res = await db.execute(sperr_query)
        sperre = sperr_res.scalar_one_or_none()
        
        if sperre:
            # Wenn ein Eintrag existiert, prüfen wir, ob das heutige Datum im Sperrzeitraum liegt
            if sperre.Von and sperre.Bis and (sperre.Von <= heute <= sperre.Bis):
                # Log schreiben (X = Abgewiesen/Sperre)
                await _write_log(db, "X", bn, client_ip, client_host)
                await db.commit()
                return "lbsp"

        is_ok, token = await auth_service.authenticate_user(bn, pw)
        is_local_user = False
        
        if not is_ok:
            local_query = select(LokalerBenutzer).where(
                LokalerBenutzer.BenNr == bn.strip()
            )
            local_res = await db.execute(local_query)
            local_user = local_res.scalar_one_or_none()

            if local_user and pw.strip() == local_user.Pw:
                if local_user.Von <= heute <= local_user.Bis:
                    is_ok = True
                    is_local_user = True
                    token = "lokal"  # Einfacher Platzhalter-Token für lokale Nutzer
                else:
                    # FALL: Lokaler Benutzer existiert, ist aber zeitlich abgelaufen
                    await _write_log(db, "X", bn, client_ip, client_host)
                    await db.commit()
                    return "lberr"
            else:
                # FALL: Passwort falsch (weder GBV noch lokaler Account matchen)
                await _write_log(db, "P", bn, client_ip, client_host)
                await db.commit()
                return "lberr"

        
        if not is_local_user:
            status = await auth_service.check_borrower_status(bn, token)
            # -1 indicates a network/backend failure in the GBV module
            if status == -1:
                if settings.paia_fail_open:
                    # Allow login but write a warning to the logs
                    await _write_log(db, "W", bn, client_ip, client_host)
                else:
                    await _write_log(db, "X", bn, client_ip, client_host)
                    await db.commit()
                    return "lbsp"
            elif status is None or status not in settings.allowed_status_codes:
                await _write_log(db, "X", bn, client_ip, client_host)
                await db.commit()
                return "lbsp"
        else:
            pass # Lokale Nutzer sind standardmäßig immer "aktiv" (0), daher keine Statusprüfung nötig

        if settings.deny_multi_login == 1:
            active_res = await db.execute(select(Aktiv).where(Aktiv.BenNr == bn, Aktiv.IP != client_ip))
            if active_res.scalar_one_or_none():
                await _write_log(db, "A", bn, client_ip, client_host)
                await db.commit()
                return "aktv"

        max_minuten = await get_user_max_minutes(bn, db)
        ende_acc_z_str = get_ende_acc_z()
        
        nutzung_query = select(Nutzung).where(Nutzung.BenNr == bn, Nutzung.Bis == ende_acc_z_str)
        nutzung_res = await db.execute(nutzung_query)
        nutzung_eintrag = nutzung_res.scalar_one_or_none()
        
        if nutzung_eintrag:
            verbraucht_min = parse_time_str_to_minutes(nutzung_eintrag.Used)
            if verbraucht_min is None:
                logger.warning("Invalid 'Used' format for bn=%s: %r", bn, nutzung_eintrag.Used)
                verbraucht_min = 0
            noch_min = max_minuten - verbraucht_min
        else:
            noch_min = max_minuten

        if noch_min <= 0:
            await _write_log(db, "Z", bn, client_ip, client_host)
            await db.commit()
            return "ende"

        if nutzung_eintrag:
            used_min = parse_time_str_to_minutes(nutzung_eintrag.Used)
            if used_min is None:
                logger.warning("Invalid 'Used' format when incrementing for bn=%s: %r", bn, nutzung_eintrag.Used)
                neuer_verbrauch_min = settings.interval_min
            else:
                neuer_verbrauch_min = used_min + settings.interval_min
            nutzung_eintrag.Used = f"{neuer_verbrauch_min // 60:02d}:{neuer_verbrauch_min % 60:02d}:00"
        else:
            stunden_max = max_minuten // 60
            minuten_max = max_minuten % 60
            max_str = f"{stunden_max:02d}:{minuten_max:02d}:00"
            used_str = "00:00:00"  # Neuer Benutzer startet mit vollem Zeitguthaben
            neuer_nutzung = Nutzung(BenNr=bn, Max=max_str, Used=used_str, Bis=ende_acc_z_str)
            db.add(neuer_nutzung)

        await db.execute(delete(Aktiv).where(Aktiv.IP == client_ip))
        neuer_aktiv = Aktiv(IP=client_ip, BenNr=bn, Host=client_host, Login=None)
        db.add(neuer_aktiv)
        
        await _write_log(db, "I", bn, client_ip, client_host)
        await db.commit()

        return f"{noch_min // 60}:{noch_min % 60:02d}"

    except Exception as e:
        logger.exception("Error in ilogin for bn=%s ip=%s host=%s", bn, client_ip, client_host)
        await db.rollback()
        return "err"


@app.post("/iloginwh", response_class=PlainTextResponse)
async def iloginwh(
    request: Request,
    bn: str = Form(...),
    ip: str = Form(None),   
    host: str = Form(None), 
    db: AsyncSession = Depends(get_db)
):
    """Dieser Endpoint wird von der Clientanwendung aufgerufen, um die verbleibende Zeit zu aktualisieren, OHNE dass ein Passwort übergeben wird.
    Er schreibt nur die verbrauchte Zeit in die DB und liefert das aktuelle Rest-Zeitguthaben zurück."""
    
    # Validate Benutzernummer (scripts should send a valid one)
    if not is_ben_nr_plausibel(bn):
        logger.warning("iloginwh: invalid ben_nr received: %r", bn)
        return "err"

    client_ip = ip if ip else request.headers.get("x-real-ip", request.client.host if request.client else None)
    if client_ip:
        if not is_valid_ip(client_ip):
            logger.warning("iloginwh: received invalid ip=%r for bn=%s", client_ip, bn)
            return "err"
    else:
        logger.warning("iloginwh: no client IP available for bn=%s", bn)
        return "err"
    client_host = host if host else request.headers.get("host", "unknown")

    try:
        max_minuten = await get_user_max_minutes(bn, db)
        ende_acc_z_str = get_ende_acc_z()
        
        nutzung_query = select(Nutzung).where(Nutzung.BenNr == bn, Nutzung.Bis == ende_acc_z_str)
        nutzung_res = await db.execute(nutzung_query)
        nutzung_eintrag = nutzung_res.scalar_one_or_none()
        
        if nutzung_eintrag:
            used_min = parse_time_str_to_minutes(nutzung_eintrag.Used)
            if used_min is None:
                logger.warning("Invalid 'Used' format when reading iloginwh for bn=%s: %r", bn, nutzung_eintrag.Used)
                used_min = 0
            neuer_verbrauch_min = used_min + settings.interval_min
            nutzung_eintrag.Used = f"{neuer_verbrauch_min // 60:02d}:{neuer_verbrauch_min % 60:02d}:00"
            noch_min = max_minuten - neuer_verbrauch_min
        else:
            stunden_max = max_minuten // 60
            minuten_max = max_minuten % 60
            max_str = f"{stunden_max:02d}:{minuten_max:02d}:00"
            used_str = "00:00:00"  # Neuer Benutzer startet mit vollem Zeitguthaben
            neuer_nutzung = Nutzung(BenNr=bn, Max=max_str, Used=used_str, Bis=ende_acc_z_str)
            db.add(neuer_nutzung)
            noch_min = max_minuten

        if noch_min <= 0:
            await db.commit()
            return "ende"

        await db.commit()
        return f"{noch_min // 60}:{noch_min % 60:02d}"

    except Exception as e:
        logger.exception("Error in iloginwh for bn=%s ip=%s host=%s", bn, client_ip, client_host)
        await db.rollback()
        return "err"

async def _write_log(db: AsyncSession, aktion: str, ben_nr: str, ip: str, host: str):
    jetzt = datetime.now()
    
    neuer_log_eintrag = LogData(
        LogAkt=aktion,
        BenNr=ben_nr.strip(),
        Datum=jetzt.date(),              # Sendet das reine Datum (YYYY-MM-DD) an Column(Date)
        Zeit=jetzt.strftime("%H:%M:%S"),  # Sendet die reine Uhrzeit (HH:MM:SS) an Column(String)
        IP=ip,
        Host=host if host else "unknown"
    )
    db.add(neuer_log_eintrag)
    logger.info("Log entry written: aktion=%s ben_nr=%s ip=%s host=%s", aktion, ben_nr, ip, host)