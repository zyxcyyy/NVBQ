# NVBQ - Неофициальный Телеграм-бот Новых Ватутинок

![NVBQ Logo](https://qu1zzly.ru/storage/nvbq-logo.png)

NVBQ - это неофициальный телеграм-бот, разработанный для упрощения взаимодействия с сервисом управления жилищными услугами "Новые Ватутинки". Бот предоставляет пользователям возможность управлять своими счетами, проверять баланс, вносить показания счетчиков и многое другое, прямо из Telegram.

## Особенности

- **Авторизация**: Возможность авторизации через номер телефона или email.
- **Информация о счете**: Просмотр баланса, истории платежей и деталей лицевого счета.
- **Управление счетчиками**: Ввод и просмотр показаний счетчиков.
- **Получение квитанций**: Загрузка квитанций за определенные периоды.
- **Пополнение баланса**: (Функция в разработке)

## Установка и Настройка

1. **Клонируйте репозиторий**:
   ```bash
   git clone https://github.com/zyxcyy/NVBQ.git
   cd NVBQ
   ```

2. **Установите зависимости**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Настройте бота**:
   - Получите токен для вашего бота через [BotFather](https://t.me/botfather) в Telegram.
   - Отредактируйте файл `config.py` и добавьте ваш токен:
     ```python
     TELEGRAM_TOKEN = 'your_telegram_bot_token'
     ```

4. **Запустите бота**:
   ```bash
   python bot.py
   ```

## Использование

0. **Проверьте версию Python**: Данный бот работает на Python версии 3.10/3.11.
1. **Запустите бота**: Отправьте команду `/start` в Telegram для начала работы с ботом.
2. **Авторизация**: Следуйте инструкциям бота для авторизации через номер телефона или email.
3. **Управление счетом**: Используйте меню бота для просмотра и управления вашим кабинетом.

## Структура Проекта

- `bot.py`: Основной файл бота.
- `config.py`: Файл конфигурации с токеном бота.
- `requirements.txt`: Список зависимостей.
- `LICENSE`: Лицензия.
- `README.md`: Документация проекта.

## Лицензия

Этот проект лицензирован под [MIT License](LICENSE).

## Контакты

Если у вас есть вопросы или предложения, пожалуйста, свяжитесь со мной - [@qu1zzlyzz](https://t.me/qu1zzlyzz).

---

Спасибо за интерес к NVBQ!
