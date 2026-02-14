FROM python:3.11-slim

WORKDIR /app

# Copier les dependances et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY *.py .

# Healthcheck basique (le process tourne)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Lancement du bot
CMD ["python", "app.py"]
