FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
ENV VITE_RESEARCH_ENABLED=true
ARG VITE_EVOLUTION_LAB=false
ARG VITE_JAEGER_UI_PATH=
RUN npm run build:production

FROM python:3.11-slim-trixie AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    SCHOLARLENS_RUNTIME_DIR=/var/lib/scholarlens FRONTEND_DIST=/srv/frontend
WORKDIR /srv
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade openssl libssl3t64 zlib1g libc6 libc-bin gzip \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libc6)" ge '2.41-12+deb13u5' \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libc-bin)" ge '2.41-12+deb13u5' \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' gzip)" ge '1.13-1+deb13u1' \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade setuptools==84.2.1 wheel==0.48.0
COPY backend/requirements-lock.txt backend/requirements-lock.txt
COPY backend/research/requirements.txt backend/research/constraints-tested.txt backend/research/pdf-layout-requirements.txt backend/research/
RUN pip install --no-cache-dir -r backend/requirements-lock.txt -r backend/research/requirements.txt -r backend/research/pdf-layout-requirements.txt \
    && useradd --uid 10001 --create-home scholar \
    && install -d -o scholar -g scholar /var/lib/scholarlens
COPY backend/ backend/
COPY agent/workflows/evidence-grounded-answer.yaml agent/workflows/
COPY .agents/skills/scholarlens-evidence-agent/SKILL.md .agents/skills/scholarlens-evidence-agent/
COPY --from=web /build/dist /srv/frontend
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2)"
CMD ["python","-m","uvicorn","backend.app1:app","--host","0.0.0.0","--port","8000","--workers","1"]

FROM app AS pdf-ocr
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
ENV SCHOLARLENS_TESSERACT=/usr/bin/tesseract
USER 10001:10001
RUN python -m backend.research.ocr_check

FROM app AS standard
