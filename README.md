# Der Ubuntu Nutzer:innen Arbeitsplatz (UNA)

An den Standorten der Technischen Informationsbibliothek (TIB) steht unseren Nutzer:innen ein neuer Recherche-Arbeitsplatz zur Verfügung, der auf dem Betriebssystem Ubuntu Linux basiert. Damit können sie nicht nur im Internet und in den lizenzierten Angeboten der TIB recherchieren, sondern auch Texte verfassen, Dokumente scannen, eine automatische Texterkennung (OCR) nutzen und drucken. 

Der Arbeitsplatz besteht aus zwei Hauptkomponenten: 

Das Hintergrundsystem (Backend **BiblioPC**): Eine Web-Anwendung auf einem zentralen Linux-Server. Sie prüft die Anmeldungen der Nutzer:innen und verwaltet deren individuelle Nutzungszeiten mithilfe einer integrierten Datenbank (SQLite). 

Der Rechner vor Ort (Ubuntu-**Client**) ist ein öffentlich zugänglicher Computer. Die Nutzer:innen melden sich dort einfach mit Ihrer Bibliotheksausweisnummer und Ihrem persönlichen Passwort an. Das System gleicht die Daten mit dem Hintergrundsystem ab und startet einen Zeit-Countdown für die Sitzung. Die Zeit läuft ab, bis man sich abmeldet oder die maximale Nutzungsdauer erreicht ist.

## Das BiblioPC Backend

Wenn auf dem Linux-Server Docker eingerichtet ist, kann einfach mit Docker-Compose und der Python Webapp **BiblioPC** gestartet werden:

```bash
git clone https://github.com/TIBHannover/BiblioPC.git
```

Anschließend die Datei mit den Umgebungsvariablen ```.env``` anpassen und einen eigenen Secret-Key eintragen wie z.B.

```SECRET_KEY="7dcnc98z4bfaazrg723fnn732z4gdbnma"```

Und eine IP-Adresse des DNS-Servers:

```DNS_SERVER_1=127.0.0.1```

Dann wird der Docker-Container gestartet:

```bash
sudo docker compose up -d --build
```
Sofern keine Änderungen an den Einstellungen vorgenommen haben, erreichen Sie die Website über die Adresse https://localhost oder Hostname bzw. IP-Adresse des Linux-Servers.

Beim ersten Aufruf zeigt der Browser eine Sicherheitswarnung bezüglich des Zertifikats an. Das liegt daran, dass das Zertifikat vom System selbst ausgestellt ("selbstsigniert") wurde. Diese Warnung kann man bedenkenlos überspringen und die Seite trotzdem öffnen. Soll die Warnmeldung dauerhaft vermieden werden, kann im Ordner ```ssl``` ein eigenes, vertrauenswürdiges Zertifikat hinterlegt werden.

Die Zugangsdaten für das Admin-Konto sind in der Datei ```.env``` gespeichert. Die Daten können dort vor dem ersten Start beliebig geändert werden.

Die Standard-Zugangsdaten sind: Benutzername ```useradmin``` und Passwort ```@ChangeMe@```.

Um schnell zu prüfen, ob die Anmeldung über einen Client grundsätzlich funktioniert, reicht ein einfacher Befehl mit *cURL*:

```
curl -k -X POST https://localhost/ilogin -d bn="99999999" -d pw="testpw123" -d host="lummerland"" -d ip="127.0.0.1"
curl -k -X POST https://localhost/iloginwh -d "bn=99999999"
curl -k -X POST https://localhost/ilogout -d host="lummerland"" -d ip="127.0.0.1"
```

Wenn die BiblioPC-App von einem anderen Rechner (Client) aus getestet werden soll, kann localhost in den Befehlen einfach durch die IP-Adresse oder den Hostnamen des Servers ersetzt werden.

Das Test-Konto (99999999) funktioniert nur, solange in der Datei ```.env``` die Einstellung ```AUTH_METHOD=local``` gesetzt ist. Hinweis zur lokalen Option: Das Modul ```auth_local.py``` dient aktuell als Orientierungshilfe. Es kann für rein lokale Tests weiterentwickelt oder als Vorlage für eigene Anmeldeverfahren genutzt werden.

GBV-Anmeldung (```AUTH_METHOD=gbv```): Wenn stattdessen die Authentifizierung über den Bibliotheksverbund GBV genutzt werden soll, benötigen wird ein gültiges GBV-Benutzerkonto benötigt. Der Ablauf bleibt identisch. Im Hintergrund gleicht das System Ausweisnummer und Passwort über die PAIA-Schnittstelle des GBV unter der Adresse https://paia.gbv.de/<ISIL> ab (hier die eigene ISIL einsetzen, zum Beispiel [https://paia.gbv.de/DE-1/](https://paia.gbv.de/DE-1/)).

Um den Systemstatus und alle Aktivitäten der Anwendung live im Terminal mitzuverfolgen:

```bash
sudo docker compose logs -f
```

## Der Ubuntu-Client

Als Client-System kann Ubuntu oder jede andere Linux-Distribution genutzt werden. Die aktuellen Skripte sind auf die Desktop-Oberfläche GNOME und deren Anmeldemaske (GNOME Display Manager / GDM) abgestimmt. Für den Testbetrieb kann ohne große Änderungen eine einfache Installation von Ubuntu (Version 24.04 oder 26.04) mit dem Standardbenutzer ```una-user``` genommen werden. Nach der Grundinstallation werden ein Fernzugriff und ein Administrator-Zugang benötigt. Für den Fernzugriff kann OpenSSH-Server installiert werden, um sich per SSH mit dem Client zu verbinden. Da ```una-user``` als einfacher Nutzer ohne Administrator-Rechte arbeitet, sollte der root-Account unter Ubuntu dauerhaft freigeschaltet werden (unter anderen Linux-Distributionen ist er meist schon vorhanden):

```bash
sudo passwd root
```

Damit root sich auch per SSH an den Test-Client anmelden kann, wird in der Datei ``` /etc/ssh/sshd_config``` die Zeile ```PermitRootLogin``` auskommentiert und der Parameter auf ```yes``` gesetzt.

### Installation des PAM-Moduls

Der flexible Anmeldedienst PAM ist ein zentrales Framework unter Linux, das die Überprüfung von Identitäten und Zugriffsrechten von den eigentlichen Anwendungsprogrammen entkoppelt. Das Skript ```una_auth.py``` prüft das Passwort und weist die Ausweisnummer automatisch dem festen Systembenutzer ```una-user``` zu. Es lässt sich bei Bedarf problemlos an andere Login-Manager (wie LightDM) anpassen.

Als root werden ```una-user``` unter Ubuntu falls nötig die administrativen Rechte entzogen und zusätzliche Programme z.B. für die Authentifizierung über das PAM-Modul installiert:

```bash
gpasswd -d una-user sudo
gpasswd -d una-user adm
apt-get update && apt-get dist-upgrade
apt-get install -y curl jq libpam-python python3-tk python3-requests
```

Wenn das erledigt ist, wird das PAM-Modul nach ```/usr/local/lib/security/``` kopiert oder dort erstellt und die Berechtigungen gesetzt:

```bash
chown root:root /usr/local/lib/security/una_auth.py
chmod 644 /usr/local/lib/security/una_auth.py
```

Die zentrale Konfigurationsdatei für das PAM-System ```common-session``` muss für das Python-Skript ```una_auth.py``` vorbereitet werden, indem die beiden Zeilen nach ```pam_unix.so``` ersetzt werden:

```
# and here are more per-package modules (the "Additional" block)
session required        pam_unix.so
session optional        pam_systemd.so
session required        pam_python.so /usr/local/lib/security/una_auth.py
# end of pam-auth-update config
```

Die JSON-Datei für die Konfiguration des PAM-Moduls wird unter ```/usr/local/etc/una-config.json``` erstellt. Die URL des Servers muss noch angepasst werden:

```
{
    "server_url": "https://10.0.3.2",
    "login_script": "ilogin",
    "logout_script": "ilogout",
    "status_script": "iloginwh"
}
```

Anschlißend muss noch die spezifische PAM-Konfigurationsdatei für den grafischen Anmeldebildschirm ```/etc/pam.d/gdm-password``` angepasst werden. Diese Datei regelt exakt, was passieren muss, wenn ein Benutzer vor dem PC sitzt und Benutzernamen und Passwort eingibt, um sich in die grafische Desktop-Umgebung GNOME einzuloggen.

```
#%PAM-1.0

# 1. Python-Modul mit User-Mapping
# Wenn das Skript PAM_SUCCESS liefert, bricht 'success=done' die weitere 
# Authentifizierung ab und GDM loggt den (im Skript umgebogenen) 'una-user' ein.
auth [success=done default=ignore] pam_python.so /usr/local/lib/security/una_auth.py

# 2. Standard GDM Authentifizierung
# Falls dein Skript 'ignore' liefert (z. B. wenn die API nicht erreichbar ist 
# oder die Eingabe leer war), greift der normale Login-Prozess.
@include common-auth

# 3. Account-Prüfung
# Hier wird gecheckt, ob der Account (una-user) überhaupt existiert und aktiv ist.
@include common-account

# 4. GDM-spezifische Erweiterungen
# Dies sorgt u.a. dafür, dass der GNOME-Keyring angestoßen wird.
auth      requisite     pam_nologin.so
auth      optional      pam_gnome_keyring.so

# 5. Session- und Environment-Variablen
# Lädt Sprach- und Systemlimits (wichtig für die Desktop-Umgebung).
session   required      pam_env.so readenv=1
session   required      pam_env.so readenv=1 envfile=/etc/default/locale
session   required      pam_limits.so
@include common-session

# 6. Passwort-Änderungen (Standard)
@include common-password
```

Die Datei ```/etc/pam.d/gnome-screensaver``` klärt, welcher Benutzer angemeldet ist, wenn der Bildschirm entsperrt werden soll. Das darf nur der ursprünglich angemeldete Benutzer:

```
#%PAM-1.0

# 1. Das Python-Modul prüft die Identität gegen /dev/shm/benutzernummer und die API
auth [success=done default=ignore] pam_python.so /usr/local/lib/security/una_auth.py

# 2. Falls das Skript 'ignore' liefert, greift die Standard-Authentifizierung
# (Wichtig, falls Admins sich lokal mit Passwort am Lockscreen legitimieren müssen)
@include common-auth

# 3. Standard Account-Prüfung
@include common-account

# 4. Session-Management für den Lockscreen
# Erlaubt dem System, den Keyring beim Entsperren wieder zu öffnen
auth      optional      pam_gnome_keyring.so
@include common-session
```

Zum Schluss soll der Benutzer vom Backend abgemeldet werden, wenn er sich vom Desktop wieder abmeldet. Dazu wird die Datei ```/usr/local/bin/una-reset.sh``` erstellt und ausführbar gemacht:

```bash
chmod +x /usr/local/bin/una-reset.sh
```

Damit das Skript ausgeführt wird, muss es in der Datei ```/etc/gdm3/PostSession/Default``` hinterlegt werden, ein systemweites Shell-Skript, das vom GDM automatisch in dem Moment ausgeführt wird, wenn sich ein Benutzer aus seiner grafischen Desktop-Sitzung abmeldet:

```bash
#!/bin/sh
/usr/local/bin/una-reset.sh
exit 0
```

Damit es bei den Nutzer:innen nicht zu Verwirrungen kommt, was bei der Anmeldung eingegeben werden muss, wird "Benutzername" im Anmeldebildschirm durch den Text "Bibliotheksausweisnummer" ersetzt. Das Skript ändert die Beschriftung in der Anmeldemaske und Benutzeroberfläche von Ubuntu:

```bash
apt-get install -y gettext language-pack-de language-pack-en language-pack-gnome-de language-pack-gnome-en
msgunfmt /usr/share/locale-langpack/de/LC_MESSAGES/gdm.mo -o /tmp/gdm_de.po
sed -i 's/Benutzername/Bibliotheksausweisnummer/g' /tmp/gdm_de.po
msgfmt /tmp/gdm_de.po -o /tmp/gdm.mo
cp /usr/share/locale-langpack/de/LC_MESSAGES/gdm.mo{,.bak}
cp /tmp/gdm.mo /usr/share/locale-langpack/de/LC_MESSAGES/gdm.mo
msgunfmt /usr/share/locale-langpack/de/LC_MESSAGES/gnome-shell.mo -o /tmp/gnome-shell_de.po
sed -i 's/Benutzername/Bibliotheksausweisnummer/g' /tmp/gnome-shell_de.po 
msgfmt /tmp/gnome-shell_de.po -o /tmp/gnome-shell.mo 
cp /usr/share/locale-langpack/de/LC_MESSAGES/gnome-shell.mo{,.bak}
cp /tmp/gnome-shell.mo /usr/share/locale-langpack/de/LC_MESSAGES/gnome-shell.mo
```

Die Änderungen können dann mit einem Neustart der Anmeldemaske übernommen werden:

```bash
systemctl restart gdm
```

Das Skript sollte jedesmal nach einem System-Update von GDM ausgeführt werden, da sonst wieder "Benutzername" in der Anmeldemaske steht.

### Sauberer Benutzerordner bei jedem Login

Jede:r Nutzer:in hinterlässt Spuren (Browser-Verläufe, Downloads, gespeicherte Passwörter, persönliche Dokumente) bei der Benutzung des öffentlichen PCs. Durch das Zurücksetzen des Benutzerordners bzw. Home-Verzeichnisses (```/home/una-user```) beim Abmelden wird garantiert, dass der/die nachfolgende Nutzer:in keinen Zugriff auf Daten der vorherigen Session hat. Außerdem können Nutzer:innen das System nicht versehentlich oder absichtlich unbrauchbar machen, z. B. durch das Löschen wichtiger Konfigurationsdateien. Deshalb soll bei jedem Login ein exakt definierter, sauberer Zustand hergestellt werden.

Umgesetzt wird das mit einem *OverlayFS*, das seit Jahren fest im Linux-Kernel integriert ist. OverlayFS legt zwei Verzeichnisse übereinander und präsentiert sie Nutzer:innen als einen einzigen Ordner (```/home/una-user```). 

Das *Lowerdir* wird als unveränderliche Master-Vorlage auf der Festplatte nach z.B. ```/opt/una-master``` kopiert. Sie enthält das vorgefertigte Home-Verzeichnis (z. B. Standard-Konto-Einstellungen, Default-Browser-Profile, Hintergründe) und wird im laufenden Betrieb nur lesend eingebunden.

Das *Upperdir* (```/dev/shm/una-upper```) liegt im Arbeitsspeicher (```/dev/shm``` ist ein RAM-Disk-Dateisystem). Es nimmt alle Schreibzugriffe auf (z. B. Downloads, geänderte Einstellungen) und wird beim Abmelden gelöscht, wodurch alle Änderungen augenblicklich verloren gehen.

Das *Workdir* (```/dev/shm/una-work```) ist ein vom Kernel benötigter Hilfsordner im RAM zur Verwaltung von atomaren Dateisystem-Operationen.

Um das OverlayFS nutzen zu können, muss der Ordner für die Master-Vorlage einmalig als root eingerichtet und die Dateien aus einem passend eingerichteten Home-Verzeichnis dorthin kopiert werden.

Zuerst den Ordner für die Master-Vorlage einrichten:

```bash
sudo mkdir -p /opt/una-master
```

Dann das Home-Verzeichnis so einrichten, wie der Benutzerordner bei jedem Login aussehen soll (z. B. mit Standard-Lesezeichen im Browser, Vorlagen im Dokumente-Ordner etc.) und anschließend, wenn alles fertig konfiguriert ist, als Benutzer root, das Home-verzeichnis in den Master-Ordner kopieren:

```bash
cp -a /home/una-user/. /opt/una-master/
```

Sobald ```/opt/una-master``` existiert und befüllt ist, kann das Verzeichnis ```/home/una-user/``` von root gelöscht werden:

```bash
rm -rf /home/una-user && mkdir /home/una-user
```

Im PAM-Modul ```/usr/local/lib/security/una_auth.py``` müssen die folgenden Zeilen für die Sitzungsverwaltung wieder aktiviert bzw. auskommentiert werden:

```python
def pam_sm_open_session(pamh, flags, argv):
    # Wir mounten nur, wenn der Zielbenutzer una-user ist
    if pamh.user == "una-user":
        try:
            # 1. RAM-Verzeichnisse erstellen
            os.makedirs("/dev/shm/una-upper", mode=0o755, exist_ok=True)
            os.makedirs("/dev/shm/una-work", mode=0o755, exist_ok=True)
            
            # 2. Mount-Befehl ausführen (voller Pfad zu /usr/bin/mount ist sicherer)
            # Wichtig: Wir nutzen die exakt funktionierenden Pfade aus deinem Test
            cmd = [
                "/usr/bin/mount", "-t", "overlay", "overlay",
                "-o", "lowerdir=/opt/una-master,upperdir=/dev/shm/una-upper,workdir=/dev/shm/una-work",
                "/home/una-user"
            ]
            subprocess.run(cmd, check=True)
            
            # 3. Besitzrechte im Mount korrigieren, damit una-user schreiben darf
            subprocess.run(["/usr/bin/chown", "-R", "una-user:una-user", "/home/una-user"], check=True)
            syslog.syslog(syslog.LOG_INFO, "UNA-AUTH: OverlayFS erfolgreich bereitgestellt.")
        except Exception as e:
            syslog.syslog(syslog.LOG_ERR, f"UNA-AUTH: Mount-Fehler: {str(e)}")
            return pamh.PAM_SESSION_ERR          
    return pamh.PAM_SUCCESS

def pam_sm_close_session(pamh, flags, argv):
    if pamh.user == "una-user":
        # Lazy unmount (-l) ist wichtig, falls noch Prozesse auf Dateien zugreifen
        subprocess.run(["/usr/bin/umount", "-l", "/home/una-user"])
        # RAM-Inhalte löschen
        subprocess.run(["/usr/bin/rm", "-rf", "/dev/shm/una-upper", "/dev/shm/una-work"])
        syslog.syslog(syslog.LOG_INFO, "UNA-AUTH: OverlayFS entfernt und RAM bereinigt.")
    return pamh.PAM_SUCCESS
```

Und die letzte Zeile in ```/usr/local/bin/una-reset.sh```, die das Home-Verzeichnis und alle Reste beim Abmelden wieder löscht:

```bash
# Home una-user löschen
rm -rf /home/una-user && mkdir /home/una-user
```

### Ausführungsrechte entziehen

Wenn die Nutzer:innen an den öffentlichen PCs nicht das Terminal oder Softwaretools installieren sollen, kann man ihnen das Ausführungsrecht für diese Anwendungen entziehen. Besitzer und Gruppenberechtigungen bleiben davon unverändert:

```bash
chmod o-x /usr/bin/software-properties-gtk 
chmod o-x /usr/bin/update-manager
chmod o-x /usr/bin/nm-connection-editor
chmod o-x /usr/bin/gnome-power-statistics
chmod o-x /usr/bin/gnome-session-properties
chmod o-x /usr/bin/gnome-system-monitor
```

Falls Snap nicht zugunsten von Flatpak deinstalliert wurde:

```bash
chmod o-x /snap/bin/snap-store
chmod o-x /snap/bin/firmware-updater
```

Der Liste können dann noch weitere Programme hinzugefügt werden. Nach System-Updates werden die Berechtigungen wieder überschrieben und das Skript muss erneut ausgeführt werden, damit die Ausführungsrecht wieder entzogen sind.

### Sperrbildschirm

Damit der Benutzername "una-user" nicht im Sperrbildschirm steht, kann er mit einem sinnvollen Infotext ersetzt werden:

```bash
usermod -c "Dieser PC ist aktuell gesperrt" una-user
```

