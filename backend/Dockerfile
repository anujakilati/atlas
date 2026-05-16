FROM python:3.11-slim
WORKDIR /app
COPY ../requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y ffmpeg libgl1 && \
    pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
