FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_PANEL_EDITION=easy
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl iputils-ping traceroute && rm -rf /var/lib/apt/lists/*
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./
COPY VERSION ./VERSION
COPY --from=frontend /build/dist ./frontend/dist
ENV PANEL_EDITION=easy
RUN mkdir -p data clients/wireguard clients/amneziawg backups static
EXPOSE 18080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18080"]
