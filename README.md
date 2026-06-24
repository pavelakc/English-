# Запуск бота на Railway (бесплатно)

## Шаг 1 — Загрузи файлы в GitHub
1. Зайди на github.com/pavelakc/English-
2. Загрузи файлы: bot.py, requirements.txt

## Шаг 2 — Зайди на Railway
1. Открой railway.app
2. Войди через GitHub
3. Нажми "New Project"
4. Выбери "Deploy from GitHub repo"
5. Выбери репозиторий English-

## Шаг 3 — Добавь переменные
В Railway → твой проект → Variables:
ANTHROPIC_API_KEY = (твой ключ от Anthropic, если есть)

## Шаг 4 — Настрой запуск
В Railway → Settings → Start Command:
python bot.py

## Готово! Бот работает 24/7 бесплатно.

## Команды бота:
/start — приветствие
/words — последние 10 слов
/stats — статистика
/learn — открыть Mini App

## Формат добавления слов:
hello - привет
give up - сдаваться
hire foreigners — нанимать иностранцев
