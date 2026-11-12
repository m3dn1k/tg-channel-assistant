FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# GigaChat (Sber) certificates chain to the Russian Trusted Root CA (Минцифры).
# Public root cert from https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt
# (the source GigaChat docs point to). Added to the system store and also loaded by app/llm.py.
COPY certs/russian_trusted_root_ca.pem /usr/local/share/ca-certificates/russian_trusted_root_ca.crt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY certs ./certs
COPY prompts ./prompts

RUN useradd --create-home --uid 1000 bot && mkdir -p /app/data && chown -R bot:bot /app
USER bot

CMD ["python", "-m", "app.main"]
