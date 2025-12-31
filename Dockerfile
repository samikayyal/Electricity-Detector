FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Default command runs the script (suitable for Cloud Run Jobs)
CMD ["python", "main.py"]
