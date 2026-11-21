FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
ENV VITE_RESEARCH_ENABLED=true
RUN npm run build:production

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    SCHOLARLENS_RUNTIME_DIR=/var/lib/scholarlens FRONTEND_DIST=/srv/frontend
WORKDIR /srv
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
