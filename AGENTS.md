# Проект: 234-ТКСТ — Telegram боты для студентов

## Архитектура

4 Telegram-бота на **Python (aiogram 3.x)** + **DeepSeek API**. Хостятся на **Render.com** (Docker).

## Боты

| Бот | Директория | Токен | Username | Назначение |
|-----|-----------|-------|----------|------------|
| Проектирование зданий | `design-bot/` | `DESIGN_BOT_TOKEN` | @Group234TKST_bot | AutoCAD, АР/КР, ГОСТ |
| Сметное дело | `estimate/` | `ESTIMATE_BOT_TOKEN` | @estimateTKST_bot | ФЕР, ТЭР, КС-2, Гранд-Смета |
| Учёт и контроль | `accounting-and-control/` | `BOT_TOKEN` | @GroupTKST_bot | Сметы, технадзор, документация |
| СМР | `SMR/` | `SMR_BOT_TOKEN` | @Group234SMRTKST_bot | Строительно-монтажные работы |

## Текущий API

**DeepSeek** — основной провайдер:
- `openrouter.py` в каждом боте (не переименован исторически)
- Текстовые запросы: `deepseek-chat`
- Изображения/скан-ПДФ: `deepseek-vl2`
- Эндпоинт: `https://api.deepseek.com/v1/chat/completions`
- Ключ: `DEEPSEEK_API_KEY` (один на всех, в `.env` каждого бота)

Colab ноутбук для локальной Ollama: `ollama_colab.ipynb` (в корне)

## Переменные окружения для Render

Каждому сервису на Render нужно задать:
- `DEEPSEEK_API_KEY` — DeepSeek API ключ
- `SMR_BOT_TOKEN` / `DESIGN_BOT_TOKEN` / `ESTIMATE_BOT_TOKEN` / `BOT_TOKEN`

Render автоматически добавляет `RENDER_EXTERNAL_URL` и `PORT`.

## Структура типового бота

```
bot/
├── __init__.py        # пустой
├── __main__.py        # точка входа (asyncio.run(main()))
├── main.py            # настройка Bot + Dispatcher + health endpoint
├── handlers/
│   ├── __init__.py    # routers = [router]
│   └── common.py      # все обработчики команд и файлов
└── services/
    ├── __init__.py
    ├── openrouter.py  # ask(prompt, image_base64) — DeepSeek API
    ├── file_reader.py # извлечение текста из PDF/DOCX, PDF→изображения
    └── docx_writer.py # текст → .docx файл
```

## Типовые неисправности

### 1. «Insufficient Balance» — закончились деньги на DeepSeek
Признак: все боты отвечают одной и той же ошибкой про баланс.
Решение: пополнить на https://platform.deepseek.com/top-up через USDT.

### 2. «429 Too Many Requests» — превышен лимит
Решение: подождать минуту и повторить.

### 3. «DEEPSEEK_API_KEY не настроен» — нет ключа на Render
Решение: зайти в Dashboard → нужный сервис → Environment → добавить `DEEPSEEK_API_KEY`.

### 4. Бот не отвечает / не стартует
Проверить логи на Render: Dashboard → сервис → Logs.
Ошибка «not set in .env» → токен бота не задан.

### 5. Ошибка 500 при обработке PDF
Возможно, битый файл или слишком много страниц. `MAX_PAGES = 30`.

## Colab Recovery (если боты переведены на Ollama)

Файл `ollama_colab.ipynb` в корне проекта.

### Быстрый запуск:
1. Открыть https://colab.research.google.com
2. File → Upload notebook → выбрать `ollama_colab.ipynb` из корня проекта
3. Runtime → Change runtime type → GPU T4 (обязательно!)
4. Запустить все ячейки (Runtime → Run all)
5. Дождаться URL вида `https://что-то.trycloudflare.com/api/chat`
6. Обновить `API_URL` в `openrouter.py` каждого бота на этот URL
7. Закоммитить и запушить на GitHub (Render перезапустит ботов)

### Если Colab отключился:
Повторить шаги 4-7. Colab живёт ~12 часов, перезапуск занимает 2-5 минут.

### Keep-alive:
В ноутбуке уже есть встроенный пинг, но можно дополнительно поставить https://cron-job.org с интервалом 5 мин на URL туннеля.

## Переключение на другую модель

Если DeepSeek недоступен, меняется только файл `openrouter.py` в каждом боте.
Структура файла едина для всех ботов; отличается только `SYSTEM_PROMPT`.

### Ollama (локально)
В `openrouter.py` заменить:
- `API_URL` → `http://localhost:11434/api/chat`
- Модель → `llava`
- Убрать авторизацию по ключу
- Формат: `{"model": "llava", "messages": [...], "stream": false}`
- Изображения: поле `"images"` в сообщении пользователя

### GigaChat
В `openrouter.py` заменить:
- `API_URL` → `https://gigachat.devices.sberbank.ru/api/v1/chat/completions`
- OAuth эндпоинт: `https://ngw.devices.sberbank.ru:9443/api/v2/oauth`
- Нужны переменные `GIGACHAT_CLIENT_ID` и `GIGACHAT_CLIENT_SECRET`
- Формат: OpenAI-совместимый (как DeepSeek)

### OpenRouter (платный)
В `openrouter.py` заменить:
- `API_URL` → `https://openrouter.ai/api/v1/chat/completions`
- `OPENROUTER_API_KEY` вместо `DEEPSEEK_API_KEY`
- Формат: OpenAI-совместимый

## Особенности кода

- Любой PDF конвертируется в изображения, отправляется в vision-модель
- DOCX → текст, идёт в текстовую модель
- `/word` — ответ в формате .docx
- Ответы длиннее 4000 символов автоматически упаковываются в .docx
- `/menu` показывает все 4 направления
- В групповых чатах бот отвечает только при упоминании (@bot) или ответе на его сообщение
