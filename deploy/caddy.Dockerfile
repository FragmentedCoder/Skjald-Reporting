FROM node:22-slim AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2.10-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/caddy-start.sh /usr/local/bin/caddy-start
# Until Skjald says otherwise: Caddy's own certificate authority.
RUN printf 'tls internal\n' > /etc/caddy/default-tls.caddy
COPY --from=build /app/build /srv
CMD ["/usr/local/bin/caddy-start"]
