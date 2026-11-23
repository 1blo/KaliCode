# Kali Code - mobile companion server
#
# Multi-stage build:
#   1. fetch the Rojo binary (used to build Roblox place files)
#   2. install the Python app
#
# Render free tier notes:
#   - free web services have no persistent disk, so the game source is
#     cloned from git at runtime (see start.sh)
#   - the container listens on $PORT (Render injects it)

# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS rojo

ARG ROJO_VERSION=7.7.1
ARG TARGETARCH=amd64

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH}" in \
      arm64) ROJO_ASSET="rojo-${ROJO_VERSION}-linux-aarch64.zip" ;; \
      *)     ROJO_ASSET="rojo-${ROJO_VERSION}-linux-x86_64.zip" ;; \
    esac; \
    curl -fsSL -o /tmp/rojo.zip \
      "https://github.com/rojo-rbx/rojo/releases/download/v${ROJO_VERSION}/${ROJO_ASSET}"; \
    unzip -o /tmp/rojo.zip -d /tmp/rojo; \
    install -m 0755 /tmp/rojo/rojo /usr/local/bin/rojo; \
    rm -rf /tmp/rojo /tmp/rojo.zip; \
    rojo --version

# --------------------------------------------------------------------------- #
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ca-certificates git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (better layer caching).
COPY pyproject.toml README.md ./
COPY kali ./kali
COPY templates ./templates
RUN pip install --no-cache-dir -e ".[server]"

# Rojo (copied from the builder stage).
COPY --from=rojo /usr/local/bin/rojo /usr/local/bin/rojo

COPY docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Where the game repository is cloned.
ENV KALI_WORKSPACE=/workspace
RUN mkdir -p /workspace

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["/app/start.sh"]
