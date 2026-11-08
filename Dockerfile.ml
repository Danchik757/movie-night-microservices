FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ml /app/ml
CMD ["uvicorn", "ml.app:app", "--host", "0.0.0.0", "--port", "8000"]
