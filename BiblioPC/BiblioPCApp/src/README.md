| Dateiname | Rolle / Kategorie | Hauptaufgabe |
| :--- | :--- | :--- |
| `auth_base.py` | Abstrakte Basisklasse | Schnittstellendefinition für alle Authentifizierungsmodule. |
| `auth_gbv.py` | Authentifizierung | Anbindung an das externe GBV/PAIA-System zur Authentifizierung und Statusprüfung (mit Retry-Logik). |
| `auth_local.py` | Authentifizierung | Lokales Fallback-/Test-Modul für Offline-Accounts. |
| `config.py` | Konfiguration | Einlesen von Systemeinstellungen und Umgebungsvariablen (`.env`) via Pydantic. |
| `database.py` | Datenbank-Engine | Einrichtung des asynchronen SQLite-Datenbanktreibers (`aiosqlite`) und Session-Management. |
| `models.py` | ORM-Modelle | SQLAlchemy-Tabellendefinitionen für das gesamte Datenmodell. |
| `utils.py` | Hilfsfunktionen | Validierungslogiken (IPs, Benutzernummern), Zeitformat-Parser und Kontingentberechnung. |
| `main.py` | Kernanwendung / API | Hauptdatei der FastAPI-Anwendung mit Web-Routes, API-Endpunkten (`ilogin`, `ilogout`, `iloginwh`) und Session-Handling. |

---

## Detaillierte Beschreibungen

### `auth_base.py`
Enthält die abstrakte Basisklasse `BaseAuthModule`, von der jedes Authentifizierungsmodul erben muss.

* **Hauptfunktionen:**
  * `authenticate_user(bn, pw)`: Abstrakte Methode zur Validierung der Anmeldedaten.
  * `check_borrower_status(bn, token)`: Abstrakte Methode zur Prüfung von Benutzersperren.

---

### `auth_gbv.py`
Implementiert die Schnittstelle zum **Gemeinsamen Bibliotheksverbund (GBV)** über das **PAIA-Protokoll**.

* **Hauptfunktionen:**
  * `authenticate_user(...)`: Sendet Login-Anfragen per HTTP POST an die PAIA-Schnittstelle. Bietet eine Retry-Logik mit exponential Backoff bei Netzwerk-/Serverfehlern (5xx).
  * `check_borrower_status(...)`: Fragt den Sperrstatus des Benutzers ab. Gibt im Fehlerfall den Sentinel-Wert `-1` zurück (für Fail-Open/Fail-Closed-Entscheidungen).

---

### `auth_local.py`
Ein lokales Authentifizierungsmodul (`LocalAuthModule`), das primär für Testzwecke oder vereinfachte lokale Setups genutzt werden kann.

* **Hauptfunktionen:**
  * Validiert Anmeldungen gegen vordefinierte lokale Kriterien ohne externe Netzwerkaufrufe.

---

### `config.py`
Verwaltet zentral alle Konfigurationsparameter mithilfe von `pydantic-settings`.

* **Hauptfunktionen:**
  * `auth_method`: Authentifizierungsmethode (`gbv` oder `local`).
  * `standard_max`: Standard-Zeitlimit in Minuten (Fallback: 120 Minuten).
  * `acc_z`: Zählintervall für Zeitkontingente (0 = täglich, 1 = wöchentlich, 2 = monatlich).
  * `paia_fail_open`: Steuert das Verhalten bei Erreichbarkeitsproblemen des PAIA-Backends (`True` = Login trotz GBV-Ausfall erlauben).
  * Validator `parse_status_codes`: Konvertiert komma-getrennte Status-Codes aus der `.env`-Datei in ein Python-Set.

---

### `database.py`
Initialisiert die asynchrone Anbindung an die SQLite-Datenbank (`BiblioPC.db`).

* **Hauptfunktionen:**
  * **Async Engine & Sessions:** Nutzt `sqlalchemy.ext.asyncio` und `aiosqlite`.
  * **WAL-Modus:** Aktiviert über SQLite-Pragmas (`PRAGMA journal_mode=WAL` und `PRAGMA synchronous=NORMAL`) eine hohe Fehlertoleranz und Performance bei simultanen Schreib-/Lesezugriffen.
  * `get_db()`: Async Generator als Dependency-Injection für FastAPI-Routen.

---

### `models.py`
Definiert alle Datenbanktabellen als SQLAlchemy-ORM-Klassen:

* `Bearbeiter`: Mitarbeiter-/Admin-Accounts für die Web-Oberfläche (Passwörter als Bcrypt-Hash).
* `Aktiv`: Derzeit angemeldete Benutzer inklusive Client-IP, Hostname und Login-Zeitpunkt.
* `LokalerBenutzer`: Vom Personal angelegte, temporäre Gast- oder Sonder-Accounts mit Gültigkeitszeitraum (`Von` bis `Bis`).
* `Sperrung`: Sperreinträge für bestimmte Benutzernummern.
* `Zeitlimit`: Globales Standard-Zeitlimit.
* `BenutzerMax` & `Zugang`: Benutzer- oder gruppenspezifische (Wildcard-)Zeitlimits.
* `Nutzung`: Dokumentiert die verbrauchte Nutzungszeit (`Used`) und das Maximallimit (`Max`) innerhalb des aktuellen Intervalls.
* `LogData`: Vollständiges Audit-Log aller Anmelde-, Abmelde- und Ablehnungsereignisse.

---

### `utils.py`
Enthält Hilfsklassen und Utility-Funktionen zur Logikabstraktion:

* `is_ben_nr_plausibel(bn)`: Prüft per Regex, ob eine Benutzernummer 8–11 Ziffern besitzt (optional mit 'x'/'X' am Ende).
* `parse_time_str_to_minutes(time_str)`: Konvertiert Zeitstrings im Format `HH:MM:SS` oder `HH:MM` robust in Minuten.
* `get_user_max_minutes(bn, db)`: Vielschichtige Ermittlung des Zeitlimits:
  1. Exakte Übereinstimmung in `BenutzerMax`.
  2. Wildcard-Matching (`123*`) – wählt das spezifischste Matching.
  3. Globaler Tabelleneintrag in `Zeitlimit`.
  4. Hardcoded Fallback (120 Minuten).
* `get_ende_acc_z()`: Errechnet den Stichtag (YYYYMMDD) für die Kontingentberechnung basierend auf `settings.acc_z`.
* `is_valid_ip(ip_str)`: Überprüft IPv4/IPv6-Adressen auf Gültigkeit.

---

### `main.py`
Der Kern der Anwendung auf Basis von FastAPI.

* **Startup & Admin-Init:** Erstellt Tabellen, initialisiert das Standard-Zeitlimit und legt den Standard-Admin `useradmin` an.
* **Session & Templates:** SessionMiddleware für Cookie-basierte Logins und Jinja2-Template-Rendering mit benutzerdefinierten Datumsfiltern (`datetime_de`).
* **Web-Routen:**
  * `/` & `/login`: Login-Seite für Bibliotheksmitarbeiter.
  * `/uebersicht`: Live-Tabelle aller aktiven PCs.
  * `/benutzerverwaltung` & `/bearbeiterverwaltung`: Verwaltung lokaler Gast-Accounts und Admin-Zugänge.
  * `/benutzersperren` & `/benutzerzeitkontingent`: Manuelle Sperren und Zeitboni.
  * `/benutzerstatistik` & `/tagesprotokoll`: Detaillierte Protokoll- und Nutzungsanalysen.
* **API-Endpunkte (Client-Schnittstellen):**
  * `POST /ilogin`: Verifiziert Anmeldedaten, prüft Sperren, errechnet Restzeit und trägt die Sitzung in `Aktiv` sowie `LogData` ein.
  * `POST /iloginwh`: Regelmäßiger Keep-Alive/Heartbeat der PCs. Aktualisiert die verbrauchte Nutzungszeit ohne Passwortübertragung.
  * `POST /ilogout`: Meldet den Benutzer anhand seiner Client-IP ab.

---

## Sicherheit, Betrieb & Best Practices

### Passwörter & Sicherheit
* **Standard-Passwörter ändern:** Bei der Erstinbetriebnahme erstellt die Anwendung das Admin-Konto `useradmin` mit dem Standardpasswort `@ChangeMe@` (siehe `config.py`). **Dieses muss umgehend in der Oberfläche geändert werden!**
* **Secret Key anpassen:** Der `secret_key` in `config.py` für die Cookie-Verschlüsselung der SessionMiddleware muss in Produktionsumgebungen über die `.env`-Datei durch einen kryptografisch sicheren Schlüssel ersetzt werden.
* **HTTPS/Reverse Proxy:** In `main.py` ist `https_only=False` gesetzt. Sobald die Anwendung hinter einem Reverse Proxy (z. B. Nginx) mit SSL-Zertifikat läuft, sollte `https_only=True` aktiviert und Cookie-Sicherheit gewährleistet werden.

### Fail-Open vs. Fail-Closed Logik (`paia_fail_open`)
* Wenn das externe GBV/PAIA-System nicht erreichbar ist, steuert `paia_fail_open` in `config.py` das Verhalten:
  * `True` (Fail-Open): Anmeldungen werden trotz PAIA-Fehlern gewährt (Ausfallschutz für Bibliothekskunden). Ereignis wird als Warnung (`W`) geloggt.
  * `False` (Fail-Closed): Anmeldungen werden bei Backend-Ausfall vorsorglich blockiert.
* **Empfehlung:** Je nach Bibliothekspolitik bewusst festlegen!

### Datenbank-Performance & SQLite Concurrency
* Durch die Verwendung von **WAL (Write-Ahead Logging)** in `database.py` wird die Parallelitätsleistung von SQLite deutlich verbessert.

### IP-Adressierung & Proxy-Header
* Die Endpunkte `ilogin`, `iloginwh` und `ilogout` identifizieren Endgeräte primär anhand der Client-IP-Adresse (`client_ip`).
* Falls die PCs über einen Proxy/Router geleitet werden, muss sichergestellt sein, dass der Proxy-Header `X-Real-IP` oder `X-Forwarded-For` korrekt an FastAPI übergeben wird. Andernfalls schlägt die Zuordnung der aktiven PCs fehlerhaft fehl!

### Zeitintervall-Einstellungen (`acc_z`)
* Wie ist `acc_z` in der `.env` konfiguriert?
  * `0`: Das Guthaben wird jeden Tag um Midnight zurückgesetzt.
  * `1`: Das Guthaben gilt pro Woche (Montag bis Sonntag).
  * `2`: Das Guthaben gilt pro Kalendermonat.
