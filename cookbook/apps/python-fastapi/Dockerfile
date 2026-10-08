FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
# One worker: runs and the result cache live in this process (see README).
# The platform sets PORT; 8000 is the local default.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
