FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads/videos /app/uploads/logos /app/staging/dataset /app/staging/kernel /app/output && \
    chmod -R 777 /app/uploads /app/staging /app/output

ENV PORT=7860
EXPOSE 7860

CMD ["python3", "app.py"]
