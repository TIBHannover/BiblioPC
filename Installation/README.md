# Installationsskripte

**una-pam-login** - Installiert das PAM-Modul auf dem Ubuntu 24.04-Client. Damit die Anmeldung funktioniert muss das Verzeichnis `/opt/una-master` mit der unveränderliche Master-Vorlage des Home-Verzeichnisses `/home/una-user` angelegt sein!

**una-pam-login_Ubuntu26-04** - Beim Upgrade auf Ubuntu 26.04 wurden die GDM-Hooks PreLogin und PostSession im Rahmen der X11-Bereinigung entfernt *). Dadurch wird `/etc/gdm3/PostSession/Default` und damit `una-reset.sh` nach dem Logout nicht mehr ausgeführt. Als Ersatz wurde der zentrale Reset über `pam_exec` in die PAM-Session-Kette integriert, wobei das Skript ausschließlich bei `PAM_TYPE=close_session` und für die GDM-Dienste `gdm-password` bzw. `gdm-autologin` läuft. Der GDM-Greeter-Dienst `gdm-launch-environment` wird explizit ausgeschlossen, damit dessen Session-Ende keinen zweiten, fehlerhaften Reset mit leeren bzw. veralteten Client-Daten auslöst.

*) https://documentation.ubuntu.com/release-notes/26.04/changes-since-previous-interim/
