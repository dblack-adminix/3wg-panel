FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py

RUN mkdir -p /app/data /app/clients/wireguard /app/clients/amneziawg /app/backups/wireguard /app/backups/amneziawg

EXPOSE 18080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18080"]
