FROM python:3.11-slim

# Setup non-root user 1000 for Hugging Face Spaces compatibility
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

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
    chown -R 1000:1000 /app && \
    chmod -R 777 /app

USER user

ENV PORT=7860
EXPOSE 7860

CMD ["python3", "app.py"]
