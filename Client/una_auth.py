import sys
import requests
import syslog
import os
import json
import subprocess
import urllib3
import socket
from urllib.parse import urlparse


CONFIG_PATH = "/usr/local/etc/una-config.json"

def get_api_url():
    """Lädt die Konfiguration und baut die API-URL zusammen."""
    if not os.path.exists(CONFIG_PATH):
        syslog.syslog(syslog.LOG_ERR, f"UNA-AUTH: {CONFIG_PATH} fehlt!")
        sys.exit(1)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            server = config.get("server_url")
            script = config.get("login_script")

            if not server or not script:
                syslog.syslog(syslog.LOG_ERR, "UNA-AUTH: Konfigurationsfelder fehlen!")
                sys.exit(1)

            return f"{server.rstrip('/')}/{script.lstrip('/')}"
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, f"UNA-AUTH: Fehler beim Laden der Config: {e}")
        sys.exit(1)

def log(msg):
    syslog.syslog(syslog.LOG_INFO, f"UNA-AUTH: {msg}")

def show_error(pamh, text):
    """Sendet eine Fehlermeldung an das GDM3 Interface."""
    try:
        msg = pamh.Message(pamh.PAM_ERROR_MSG, text)
        pamh.conversation(msg)
    except Exception:
        pass

def pam_sm_authenticate(pamh, flags, argv):
    user = None
    # 1. Versuche den User zu holen (GDM Context)
    try:
        user = pamh.get_user(None)
    except Exception:
        pass

    # 2. Login/Lockscreen Logik
    if user is None or user == "una-user":
        try:
            resp = pamh.conversation(pamh.Message(pamh.PAM_PROMPT_ECHO_ON, "Bibliotheksausweisnummer: "))
            user = resp.resp
        except Exception:
            return pamh.PAM_CONV_ERR

    if not user:
        return pamh.PAM_USER_UNKNOWN

    # 3. Passwort abfragen
    try:
        resp = pamh.conversation(pamh.Message(pamh.PAM_PROMPT_ECHO_OFF, "Passwort: "))
        password = resp.resp
    except Exception:
        return pamh.PAM_CONV_ERR

    # 4. API Abfrage
    api_url = get_api_url()

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    try:
        parsed_url = urlparse(api_url)
        api_host = parsed_url.hostname

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((api_host, 80))
        client_ip = s.getsockname()[0]
        s.close()
    except Exception:
        client_ip = "127.0.0.1"

    payload = {
        "bn": user,
        "pw": password,
        "host": hostname,
        "ip": client_ip
    }
    
    # Fehler-Mapping definieren
    errors = {
        "lberr": "Benutzernummer oder Passwort falsch.",
        "sper": "Ihr Account ist gesperrt. Bitte wenden Sie sich an die Information.",
        "lbsp": "Problem mit dem Bibliothekskonto (LBS).",
        "ende": "Ihre tägliche Nutzungszeit ist abgelaufen.",
        "aktv": "Sie sind bereits an einem anderen PC angemeldet.",
        "err":  "Datenbankfehler. Bitte versuchen Sie es später erneut."
    }

    try:
        # Timeout auf 5 Sekunden setzen, damit GDM nicht einfriert
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.post(api_url, data=payload, timeout=5, verify=False)
        response_text = r.text.strip()

        # FALL: ERFOLG
        if r.status_code == 200 and ":" in response_text:
            
            # Check ob Session bereits von jemand anderem belegt (Lockscreen-Schutz)
            if os.path.exists("/dev/shm/benutzernummer"):
                with open("/dev/shm/benutzernummer", "r") as f:
                    current_session_user = f.read().strip()
                
                if user != current_session_user:
                    log(f"LOCKSCREEN: Abgelehnt. {user} wollte Session von {current_session_user} öffnen.")
                    show_error(pamh, "Dieser PC ist durch einen anderen Benutzer belegt.")
                    return pamh.PAM_AUTH_ERR

            log(f"Login erfolgreich für {user}. Mapping auf una-user.")
            
            # WICHTIG: User auf lokalen Account umbiegen
            pamh.user = "una-user"
            
            # Session-Daten hinterlegen
            for filename, value in [("benutzernummer", user), ("hostname", hostname), ("ip", client_ip)]:
                filepath = f"/dev/shm/{filename}"
                with open(filepath, "w") as f:
                    f.write(value)
                os.chmod(filepath, 0o644)
            
            return pamh.PAM_SUCCESS

        # FALL: API ANTWORTET MIT FEHLERCODE (z.B. nopw)
        error_msg = errors.get(response_text, f"Anmeldefehler (Code: {response_text})")
        show_error(pamh, error_msg)
        log(f"Login abgelehnt für {user}: {response_text}")
        return pamh.PAM_AUTH_ERR

    except requests.exceptions.RequestException as e:
        # Dies fängt Timeouts, Verbindungsabbrüche und DNS-Fehler ab
        show_error(pamh, "Server nicht erreichbar.")
        log(f"Netzwerkfehler: {str(e)}")
        return pamh.PAM_SERVICE_ERR
    except Exception as e:
        # Alles andere (Skriptfehler)
        show_error(pamh, "Interner Systemfehler.")
        log(f"Allgemeiner Fehler im PAM-Skript: {str(e)}")
        return pamh.PAM_SERVICE_ERR

def pam_sm_setcred(pamh, flags, argv):
    return pamh.PAM_SUCCESS

def pam_sm_acct_mgmt(pamh, flags, argv):
    return pamh.PAM_SUCCESS

def pam_sm_open_session(pamh, flags, argv):
    # Wir mounten nur, wenn der Zielbenutzer una-user ist
    if pamh.user == "una-user":
        try:
            # 1. RAM-Verzeichnisse erstellen
 #           os.makedirs("/dev/shm/una-upper", mode=0o755, exist_ok=True)
 #           os.makedirs("/dev/shm/una-work", mode=0o755, exist_ok=True)
            
            # 2. Mount-Befehl ausführen (voller Pfad zu /usr/bin/mount ist sicherer)
            # Wichtig: Wir nutzen die exakt funktionierenden Pfade aus deinem Test
 #           cmd = [
 #               "/usr/bin/mount", "-t", "overlay", "overlay",
 #               "-o", "lowerdir=/opt/una-master,upperdir=/dev/shm/una-upper,workdir=/dev/shm/una-work",
 #               "/home/una-user"
 #           ]
 #           subprocess.run(cmd, check=True)
            
            # 3. Besitzrechte im Mount korrigieren, damit una-user schreiben darf
 #           subprocess.run(["/usr/bin/chown", "-R", "una-user:una-user", "/home/una-user"], check=True)
            
            syslog.syslog(syslog.LOG_INFO, "UNA-AUTH: OverlayFS erfolgreich bereitgestellt.")
        except Exception as e:
            syslog.syslog(syslog.LOG_ERR, f"UNA-AUTH: Mount-Fehler: {str(e)}")
            return pamh.PAM_SESSION_ERR
            
    return pamh.PAM_SUCCESS

def pam_sm_close_session(pamh, flags, argv):
    if pamh.user == "una-user":
        # Lazy unmount (-l) ist wichtig, falls noch Prozesse auf Dateien zugreifen
 #       subprocess.run(["/usr/bin/umount", "-l", "/home/una-user"])
        # RAM-Inhalte löschen
 #       subprocess.run(["/usr/bin/rm", "-rf", "/dev/shm/una-upper", "/dev/shm/una-work"])
        syslog.syslog(syslog.LOG_INFO, "UNA-AUTH: OverlayFS entfernt und RAM bereinigt.")
    return pamh.PAM_SUCCESS
        