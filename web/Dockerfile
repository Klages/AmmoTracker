FROM nginx:alpine

# Kopiere das statische Frontend
COPY ./web /usr/share/nginx/html

# Kopiere die Nginx-Konfiguration
COPY ./nginx.conf /etc/nginx/conf.d/default.conf
