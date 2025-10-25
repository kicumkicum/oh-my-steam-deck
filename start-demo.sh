#!/bin/bash

# Скрипт для запуска демо-страницы Retrowave Theme

echo "🎨 Запуск демо-страницы Retrowave Theme..."
echo ""

# Проверяем наличие файлов
if [ ! -f "retrowave-demo.html" ]; then
    echo "❌ Файл retrowave-demo.html не найден!"
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

# Пытаемся открыть в браузере
if command -v xdg-open &> /dev/null; then
    echo "🌐 Открываем в браузере..."
    xdg-open retrowave-demo.html
elif command -v open &> /dev/null; then
    echo "🌐 Открываем в браузере..."
    open retrowave-demo.html
elif command -v start &> /dev/null; then
    echo "🌐 Открываем в браузере..."
    start retrowave-demo.html
else
    echo "⚠️  Не удалось автоматически открыть браузер."
    echo "📁 Откройте файл retrowave-demo.html в браузере вручную."
fi

echo ""
echo "🎵 Добро пожаловать в мир Retrowave!"
echo "💡 Для лучшего опыта включите звук в браузере."
echo ""
echo "📖 Документация: RETROWAVE-THEME-README.md"
