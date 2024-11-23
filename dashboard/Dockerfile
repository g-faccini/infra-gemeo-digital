FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5046

CMD ["streamlit", "run", "dashboard.py","--server.port=5046"]
