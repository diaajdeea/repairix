FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-neon.txt ./
RUN pip install --no-cache-dir -r requirements-neon.txt "gunicorn>=22"
COPY . .
# كل البيانات والصور بقاعدة Neon (DATABASE_URL)، فالحاوية بلا حالة وبتقدر تشغّل أكثر من نسخة
ENV PYTHONUNBUFFERED=1 USE_NEON=1
CMD exec gunicorn --bind :${PORT:-8080} --workers 2 --threads 8 --timeout 120 wsgi:application
