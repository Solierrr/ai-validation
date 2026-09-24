FROM python:latest

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | bash \
    && apt-get update && apt-get install -y infisical \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]