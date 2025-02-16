FROM python:3.10-slim

# Prevents Python from writing .pyc files to disc and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including Node.js and npm for markdown formatting,
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Setting working directory in the container
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt


COPY ./api /app/api
COPY functions.txt /app/functions.txt

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
