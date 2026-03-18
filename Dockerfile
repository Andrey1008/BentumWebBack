FROM python:3.13-slim AS builder

RUN mkdir /app

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --upgrade pip 

COPY requirements.txt /app/

RUN apt update && apt install -y python3-dev default-libmysqlclient-dev build-essential pkg-config libmariadb3 curl

RUN pip install --force --no-cache --no-cache-dir -r requirements.txt

FROM python:3.13-slim

RUN useradd -m -r appuser && \
   mkdir /app && \
   chown -R appuser /app

COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

WORKDIR /app

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 1337

CMD ["gunicorn", "--bind", "0.0.0.0:1337", "--workers", "3", "backend.wsgi:application"]

