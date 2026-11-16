# Image commune aux quatre services : chaque conteneur lance un module différent.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY restaurant ./restaurant
COPY commande ./commande
COPY livraison ./livraison
COPY suivi ./suivi

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/sante', timeout=2)"
