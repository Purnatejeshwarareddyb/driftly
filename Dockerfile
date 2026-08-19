FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

ENV DRIFTLY_HOST=0.0.0.0 \
    DRIFTLY_PORT=8080 \
    DATABASE_URL=sqlite:////app/data/driftly.db

EXPOSE 8080

CMD ["python", "main.py"]
