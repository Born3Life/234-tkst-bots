#!/usr/bin/env bash
# Развёртывание 5 ботов 234-ТКСТ на VPS (Ubuntu 24.04)
# Запуск: sudo bash deploy.sh
set -euo pipefail

BOTS=(assistant-bot design-bot estimate accounting-and-control SMR)
SPECIAL=(design-bot estimate accounting-and-control SMR)

if [[ $EUID -ne 0 ]]; then
  echo "Запусти от root: sudo bash deploy.sh"
  exit 1
fi

# 1. Docker + compose plugin
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Установка Docker..."
  apt-get update -qq
  apt-get install -y -qq docker.io docker-compose-v2
  systemctl enable --now docker
fi

# 2. Клонирование репозитория (публичный, без авторизации)
if [[ ! -d .git ]]; then
  git clone https://github.com/Born3Life/234-tkst-bots.git .
fi

# 3. .env: создать из примера, если файла нет
for d in "${BOTS[@]}"; do
  if [[ ! -f "$d/.env" ]]; then
    cp "$d/.env.example" "$d/.env"
    echo "!! $d/.env создан из примера - впиши токены!"
  fi
done

# 4. Подписки: специализированные боты ходят к assistant по compose-DNS
for d in "${SPECIAL[@]}"; do
  sed -i 's|^ASSISTANT_BOT_URL=.*|ASSISTANT_BOT_URL=http://assistant:8080|' "$d/.env"
  grep -q '^ASSISTANT_BOT_URL=' "$d/.env" || echo 'ASSISTANT_BOT_URL=http://assistant:8080' >> "$d/.env"
done

# 5. Keep-alive к мёртвому Render больше не нужен
for d in "${BOTS[@]}"; do
  sed -i '/^RENDER_URL=/d' "$d/.env"
done

# 6. Сборка и запуск
docker compose up -d --build

# 7. Проверка health-эндпоинтов (до 60 секунд)
echo "==> Проверка health:"
for p in 8081 8082 8083 8084 8085; do
  ok=""
  for _ in $(seq 1 12); do
    if curl -fsS -m 3 "http://localhost:$p/" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 5
  done
  if [[ -n "$ok" ]]; then
    echo ":$p OK"
  else
    echo ":$p НЕ ОТВЕЧАЕТ - смотри: docker compose logs --tail=50"
  fi
done

docker compose ps
echo "==> Готово. Логи: docker compose logs -f"
