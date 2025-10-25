#!/bin/bash

# Скрипт для запуска Steam Deck Manager с Retrowave темой

echo "🎮 Запуск Steam Deck Manager - Retrowave Edition..."
echo ""

# Проверяем наличие файлов
if [ ! -f "steam-deck-manager.html" ]; then
    echo "❌ Файл steam-deck-manager.html не найден!"
    exit 1
fi

if [ ! -f "retrowave-theme.css" ]; then
    echo "❌ Файл retrowave-theme.css не найден!"
    exit 1
fi

if [ ! -f "retrowave-effects.js" ]; then
    echo "❌ Файл retrowave-effects.js не найден!"
    exit 1
fi

echo "✅ Все файлы найдены!"
echo ""

# Проверяем, запущен ли веб-сервер
if pgrep -f "python.*http.server" > /dev/null; then
    echo "🌐 Веб-сервер уже запущен"
    PORT=$(pgrep -f "python.*http.server" | xargs ps -p | grep -o ":[0-9]*" | head -1 | cut -d: -f2)
    if [ -z "$PORT" ]; then
        PORT=8000
    fi
else
    echo "🚀 Запуск веб-сервера..."
    PORT=8000
    python3 -m http.server $PORT > /dev/null 2>&1 &
    sleep 2
fi

echo "🌐 Steam Deck Manager доступен по адресу:"
echo "   http://localhost:$PORT/steam-deck-manager.html"
echo ""

# Пытаемся открыть в браузере
if command -v xdg-open &> /dev/null; then
    echo "🌐 Открываем в браузере..."
    xdg-open "http://localhost:$PORT/steam-deck-manager.html"
elif command -v open &> /dev/null; then
    echo "🌐 Открываем в браузере..."
    open "http://localhost:$PORT/steam-deck-manager.html"
elif command -v start &> /dev/null; then
    echo "🌐 Открываем в браузере..."
    start "http://localhost:$PORT/steam-deck-manager.html"
else
    echo "⚠️  Не удалось автоматически открыть браузер."
    echo "📁 Откройте http://localhost:$PORT/steam-deck-manager.html в браузере вручную."
fi

echo ""
echo "🎵 Добро пожаловать в мир Retrowave управления Steam Deck!"
echo "💡 Для остановки сервера нажмите Ctrl+C"
echo ""

# Показываем статус
echo "📊 Статус сервера:"
echo "   Порт: $PORT"
echo "   PID: $(pgrep -f "python.*http.server" | head -1)"
echo ""

# Ожидаем завершения
trap 'echo ""; echo "🛑 Остановка сервера..."; pkill -f "python.*http.server"; echo "✅ Сервер остановлен"; exit 0' INT

echo "🔄 Сервер работает... (Ctrl+C для остановки)"
wait
