FROM python:3.12-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install bird CLI for Twitter/X cookie-based data access
# Pinned to 0.8.0 — upstream @steipete/bird is deprecated, repo may be deleted
RUN npm install -g @steipete/bird@0.8.0

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/static/avatars

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Security: Run as non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser && \
    chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
# --forwarded-allow-ips: uvicorn only honours X-Forwarded-* from a trusted peer,
# and defaults that trust to 127.0.0.1. Caddy reaches us over the compose network
# (172.18.0.0/16), so the default silently discarded X-Forwarded-Proto: the app
# believed every request was plain HTTP and built redirect Locations as http://.
# Caddy then bounced those back to https://, producing a redirect ping-pong that
# browsers cache as a permanent redirect. The backend is not published to the
# host, so its only reachable peer is the proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
