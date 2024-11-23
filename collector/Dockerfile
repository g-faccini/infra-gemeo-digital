FROM python:3.9-slim

WORKDIR /app

# Instala as dependências do sistema necessárias para o speedtest-cli
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collector.py .

CMD ["python", "collector.py"]