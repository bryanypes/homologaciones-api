#!/usr/bin/env bash
set -e

echo "Bajando contenedores y eliminando volumen..."
docker compose down -v

echo "Levantando servicios de infraestructura..."
docker compose up -d postgres redis kafka

echo "Esperando que postgres este listo..."
until [ "$(docker inspect --format '{{.State.Health.Status}}' homologaciones-api-postgres-1 2>/dev/null)" = "healthy" ]; do
  sleep 2
done

echo "Corriendo migraciones..."
uv run python -m alembic upgrade head

echo "Base de datos lista."
