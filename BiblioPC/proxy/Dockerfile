FROM nginx:alpine

# OpenSSL installieren, um Zertifikate generieren zu können
RUN apk add --no-cache openssl

# Ordner für Zertifikate erstellen
RUN mkdir -p /etc/nginx/ssl

# Ein selbstsigniertes Zertifikat für die lokale Entwicklung/Testphase generieren
RUN openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/server.key \
    -out /etc/nginx/ssl/server.crt \
    -subj "/C=DE/ST=State/L=City/O=Organization/OU=IT/CN=localhost"

# Die eigene Konfiguration hineinkopieren
COPY nginx.conf /etc/nginx/conf.d/default.conf
