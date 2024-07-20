import requests
import logging
import sqlite3
import re
from warnings import filterwarnings
from config import TELEGRAM_TOKEN
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.warnings import PTBUserWarning
from datetime import datetime

# Задаем состояния разговора
CHOOSING_METHOD, PHONE, EMAIL, PASSWORD, SMS_CODE = range(5)
SELECT_YEAR, SELECT_MONTH, SEND_RECEIPT = range(3)
SELECT_METER, INPUT_READING = range(2)

# URL для получения кода и авторизации
SMS_CODE_URL = "https://nvs.domopult.ru/api/tenants-registration/code"
LOGIN_URL = "https://nvs.domopult.ru/api/tenants-registration/login"
PERSONAL_ACCOUNT_URL = "https://nvs.domopult.ru/api/api/personal_account/payments/{personal_account_id}?query=&sort=&page=0&size=15"
CLIENTS_CONFIGURATION_ITEMS_URL = "https://nvs.domopult.ru/api/api/clients/configuration-items"

ascii_art = """
        ██████╗ ██╗   ██╗     ██████╗ ██╗   ██╗ ██╗███████╗███████╗██╗     ██╗   ██╗███████╗███████╗    
        ██╔══██╗╚██╗ ██╔╝    ██╔═══██╗██║   ██║███║╚══███╔╝╚══███╔╝██║     ╚██╗ ██╔╝╚══███╔╝╚══███╔╝    
        ██████╔╝ ╚████╔╝     ██║   ██║██║   ██║╚██║  ███╔╝   ███╔╝ ██║      ╚████╔╝   ███╔╝   ███╔╝     
        ██╔══██╗  ╚██╔╝      ██║▄▄ ██║██║   ██║ ██║ ███╔╝   ███╔╝  ██║       ╚██╔╝   ███╔╝   ███╔╝      
        ██████╔╝   ██║       ╚██████╔╝╚██████╔╝ ██║███████╗███████╗███████╗   ██║   ███████╗███████╗    
        ╚═════╝    ╚═╝        ╚══▀▀═╝  ╚═════╝  ╚═╝╚══════╝╚══════╝╚══════╝   ╚═╝   ╚══════╝╚══════╝ 
        NVBQ - Неофициальный бот района "Новые Ватутинки". Версия: 1.0.0 (20 июля 2024г.)
    """
print(ascii_art)

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)
logger = logging.getLogger(__name__)

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

def init_db():
    conn = sqlite3.connect('tokens.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_tokens (
            telegram_id INTEGER PRIMARY KEY,
            auth_token TEXT NOT NULL,
            personal_account_id TEXT
        )
    ''')
    conn.commit()
    conn.close()


def save_token(telegram_id, auth_token):
    conn = sqlite3.connect('tokens.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO user_tokens (telegram_id, auth_token)
        VALUES (?, ?)
    ''', (telegram_id, auth_token))
    conn.commit()
    conn.close()

def get_token(telegram_id):
    conn = sqlite3.connect('tokens.db')
    c = conn.cursor()
    c.execute('SELECT auth_token FROM user_tokens WHERE telegram_id = ?', (telegram_id,))
    token = c.fetchone()
    conn.close()
    return token[0] if token else None

def get_personal_account_id(user_id):
    conn = sqlite3.connect('tokens.db')
    c = conn.cursor()
    c.execute('SELECT personal_account_id FROM user_tokens WHERE telegram_id = ?', (user_id,))
    personal_account_id = c.fetchone()
    conn.close()
    return personal_account_id[0] if personal_account_id else None

def delete_token(telegram_id):
    conn = sqlite3.connect('tokens.db')
    c = conn.cursor()
    c.execute('DELETE FROM user_tokens WHERE telegram_id = ?', (telegram_id,))
    conn.commit()
    conn.close()

def save_personal_account_id(user_id, personal_account_id):
    conn = sqlite3.connect('tokens.db')
    c = conn.cursor()
    c.execute('UPDATE user_tokens SET personal_account_id = ? WHERE telegram_id = ?', (personal_account_id, user_id))
    conn.commit()
    conn.close()

def parse_and_format_data(data):
    results = data.get('results', [])
    if not results:
        return "Нет данных для отображения."

    messages = []
    for result in results:
        personal_account = result.get('personalAccount', {})
        client = result.get('client', {})
        contact = client.get('contact', {})
        basic_config_item = contact.get('basicConfigurationItem', {})
        creation_method = result.get('creationMethod', 'Не указан')
        login_methods = [method.get('key') for method in result.get('loginMethods', [])]
        login_methods_message = ', '.join(login_methods) if login_methods else 'Не указаны'


        # Дата создания
        creation_date = result.get('creationDate')
        if creation_date:
            creation_date = datetime.fromisoformat(creation_date.replace('Z', '+00:00')).strftime('%d.%m.%Y %H:%M:%S')

        # Долговая информация
        debtor_info = result.get('debtorInfo', {})
        is_debtor = debtor_info.get('isDebtor', False)
        service_overall_debt = debtor_info.get('serviceOverallDebt')
        debt_message = "Нет долгов" if not is_debtor else f"Общий долг: {service_overall_debt or 'Не указан'}"

        # Группы CI
        ci_groups = personal_account.get('configurationItem', {}).get('ciGroups', [])
        ci_groups_message = '\n'.join([
            f"  ID: {group.get('id')} - Название: {group.get('name')} ({group.get('description')})"
            for group in ci_groups
        ]) or 'Нет групп CI'

        message = (
            f"  {creation_date}:\n"
            f"      ID: {result.get('id')}\n"
            f"      ID транзакции: {result.get('transactionalId')}\n"
            f"      Статус: {result.get('status')}\n"   
            f"      Тип платежа: {result.get('paymentType')}\n"
            f"      Тип сервиса: {result.get('serviceType')}\n"
            f"      Баланс: {result.get('balance')} ₽\n"
            f"      Сумма платежа: {result.get('paymentSum')} ₽\n"
            f"      Страхование: {result.get('paymentInsurance')}₽\n"
            f"      Сумма без страхования: {result.get('paymentSumWithoutInsurance')} ₽\n\n"
        )
        messages.append(message)

    personal_account_info = (
        f"Личный счет:\n"
        f"  ID: {personal_account.get('id')}\n"
        f"  Номер: {personal_account.get('number')}\n"
        f"  Баланс по коммунальным услугам: {personal_account.get('utilitiesBalance')} ₽\n"
        f"  Баланс по ремонту: {personal_account.get('repairsBalance')} ₽\n"
        f"  Активен: {'Да' if personal_account.get('isActive') else 'Нет'}\n\n"
    )

    client_info = (
        f"Клиент:\n"
        f"  ID: {client.get('id')}\n"
        f"  Имя: {contact.get('name')}\n"
        f"  Телефон: {contact.get('phone')}\n"
        f"  Email: {contact.get('emails', [{}])[0].get('email', 'Не указан')}\n"
        f"  Рекламные рассылки: {contact.get('advertisingMailing')}\n\n"
    )

    basic_config_item_info = (
        f"Информация о месте проживания:\n"
        f"  ID: {basic_config_item.get('id')}\n"
        f"  Название: {basic_config_item.get('name')}\n"
        f"  Адрес: {basic_config_item.get('address', {}).get('location')}\n"
        f"  Категория: {basic_config_item.get('category', {}).get('name')}\n"
        f"  Тип помещения: {basic_config_item.get('roomType')}\n"
        f"  Парковка: {'Да' if basic_config_item.get('hasParking') else 'Нет'}\n"
        f"  Игровая площадка: {'Да' if basic_config_item.get('hasPlayground') else 'Нет'}\n"
        f"  Спортивная площадка: {'Да' if basic_config_item.get('hasSportsGround') else 'Нет'}\n"
        f"  Включены счетчики: {'Горячая вода' if basic_config_item.get('meterFlags', {}).get('hotWaterAllowed') else ''} "
        f"{'Холодная вода' if basic_config_item.get('meterFlags', {}).get('coldWaterAllowed') else ''}\n"
        f"  Метод создания: {creation_method}\n"
        f"  Методы входа: {login_methods_message}\n"
        f"  Долговая информация: {debt_message}\n\n"
    )

    ci_groups_info = (
        f"Группы CI:\n{ci_groups_message}\n\n"
    )

    combined_message = (
        f"{client_info}"
        f"{personal_account_info}"
        f"{basic_config_item_info}"
        f"Недавние платежи:\n"
        f"{''.join(messages)}"
        f"{ci_groups_info}"
    )

    return combined_message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    first_name = user.first_name
    user_id = user.id

    auth_token = get_token(user_id)
    if auth_token:
        await account_info(update, context)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("📞 Войти по номеру телефона", callback_data='phone')],
        [InlineKeyboardButton("📧 Войти по почте", callback_data='email')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_message = await update.message.reply_text(
        f" *👋 Добро пожаловать, {first_name}!*\n└ Пожалуйста, выберите метод входа.",
        reply_markup=reply_markup,
        parse_mode='MARKDOWN'
    )
    context.user_data['start_message_id'] = sent_message.message_id
    return CHOOSING_METHOD

async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == 'phone':
        await query.edit_message_text(text="*🔐 Авторизация.*\n└ Пожалуйста, введите номер телефона, привязаннный к приложению в формате +7XXXXXXXXXX.", parse_mode='MARKDOWN')
        return PHONE
    elif choice == 'email':
        await query.edit_message_text(text="*🔐 Авторизация.*\n└ Пожалуйста, введите свой адрес электронной почты, привязаннный к приложению.", parse_mode='MARKDOWN')
        return EMAIL
    else:
        await query.edit_message_text(text="*❌ Неизвестный метод авторизации.*\n└ Пожалуйста, выберите метод входа снова.", parse_mode='MARKDOWN')
        return CHOOSING_METHOD

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text
    if not phone.startswith('+7') or len(phone) != 12:
        await update.message.reply_text(
            "*🔐 Авторизация.*\n└ Неверный формат номера. Пожалуйста, введите номер телефона, привязаннный к приложению в формате +7XXXXXXXXXX.",
            parse_mode='MARKDOWN'
        )
        return PHONE

    chat_id = update.message.chat_id
    response = requests.post(SMS_CODE_URL, json={"phone": phone})
    if response.status_code == 200:
        await update.message.delete()

        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        start_message_id = context.user_data.get('start_message_id')
        if start_message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=start_message_id,
                text="*✅ Сообщение с кодом успешно отправлено.*\n└ Пожалуйста, введите полученный код.",
                reply_markup=reply_markup,
                parse_mode='MARKDOWN'
            )

        context.user_data['phone_msg_id'] = start_message_id
        context.user_data['phone'] = phone
        return SMS_CODE
    else:
        await update.message.reply_text(
            "*❌ Ошибка при отправке СМС-кода.*\n└ Пожалуйста, попробуйте снова.", parse_mode='MARKDOWN'
        )
        return PHONE

async def email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text
    
    # Проверка на наличие русских символов в пароле
    if re.search(r'[а-яА-Я]', email):
        await update.message.reply_text("*❌ Авторизация.*\n└ Пароль не должен содержать русские символы. Пожалуйста, введите пароль снова.", parse_mode='MARKDOWN')
        return EMAIL
    
    context.user_data['email'] = email
    chat_id = update.message.chat_id

    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data='cancel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    start_message_id = context.user_data.get('start_message_id')
    if start_message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=start_message_id,
            text="*🔐 Авторизация.*\n└ Пожалуйста, введите ваш пароль, от аккаунта:", 
            parse_mode='MARKDOWN', 
            reply_markup=reply_markup
        )
    context.user_data['email_msg_id'] = start_message_id
    await update.message.delete()
    return PASSWORD

async def password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text
    context.user_data['password'] = password

    email = context.user_data.get('email')
    if not email:
        await update.message.reply_text(
            "*❌ Ошибка. Пожалуйста, повторите попытку авторизации.*", parse_mode='MARKDOWN'
        )
        return CHOOSING_METHOD

    response = requests.post(LOGIN_URL, json={
        "email": email,
        "password": password,
        "loginMethod": "PERSONAL_OFFICE"
    })

    if response.status_code == 200:
        auth_token = response.text.strip()
        if auth_token:
            save_token(update.effective_user.id, auth_token)

            await update.message.delete()

            await account_info(update, context)

            email_msg_id = context.user_data.get('email_msg_id')
            if email_msg_id:
                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=email_msg_id)

            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "*❌ Ошибка получения токена.*\n└ Пожалуйста, попробуйте снова.", parse_mode='MARKDOWN'
            )
            return EMAIL
    else:
        await update.message.reply_text(
            "*❌ Ошибка авторизации по почте.*\n└ Пожалуйста, проверьте почту/пароль и попробуйте снова.", parse_mode='MARKDOWN'
        )
        return 

async def sms_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sms_code = update.message.text
    user_id = update.effective_user.id
    phone = context.user_data.get('phone')
    if not phone:
        await update.message.reply_text(
            "*❌ Ошибка.*\n└ Пожалуйста, начните процесс авторизации заново.", parse_mode='MARKDOWN'
        )
        return ConversationHandler.END

    response = requests.post(LOGIN_URL, json={"phone": phone, "code": sms_code})
    if response.status_code == 200:
        auth_token = response.text.strip()
        print(auth_token)
        if auth_token:
            save_token(user_id, auth_token)
            await update.message.delete()

            phone_msg_id = context.user_data.get('phone_msg_id')
            if phone_msg_id:
                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=phone_msg_id)

            await account_info(update, context)

            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "*❌ Ошибка получения токена.*\n└ Пожалуйста, попробуйте снова.", parse_mode='MARKDOWN'
            )
            return CHOOSING_METHOD
    else:
        await update.message.reply_text(
            "*❌ Ошибка авторизации.*\n└ Пожалуйста, проверьте код и попробуйте снова.", parse_mode='MARKDOWN'
        )
        return PHONE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="*✅ Процесс авторизации отменен.*", parse_mode='MARKDOWN')
    return ConversationHandler.END

async def account_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    auth_token = get_token(user_id)

    if not auth_token:
        if update.message:
            await update.message.reply_text(
                "*❌ Ваша авторизация не завершена.*\n└ Пожалуйста, пройдите процесс авторизации.", parse_mode='MARKDOWN'
            )
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                "*❌ Ваша авторизация не завершена.*\n└ Пожалуйста, пройдите процесс авторизации.", parse_mode='MARKDOWN'
            )
        return

    headers = {
        'X-Auth-Tenant-Token': f'{auth_token}',
        'Content-Type': 'application/json'
    }

    try:
        # Запрос для получения данных о клиенте
        response = requests.get(CLIENTS_CONFIGURATION_ITEMS_URL, headers=headers)

        if response.status_code == 200:
            data = response.json()
            items = data.get('items', [])
            if items:
                personal_account_id = items[0].get('personalAccount', {}).get('id')
                if personal_account_id:
                    save_personal_account_id(user_id, personal_account_id)

                    # Теперь используем personal_account_id в URL
                    url = PERSONAL_ACCOUNT_URL.format(personal_account_id=personal_account_id)

                    # Продолжаем с запросом данных о личном счете
                    response = requests.get(url, headers=headers)

                    if response.status_code == 200:
                        data = response.json()
                        context.user_data['account_data'] = data  # Сохраняем данные в контекст
                        
                        # Извлекаем необходимую информацию
                        personal_account = data.get('results', [{}])[0].get('personalAccount', {})
                        balance = personal_account.get('utilitiesBalance','Неизвестно')
                        account_number = personal_account.get('number', 'Неизвестно')
                        address = personal_account.get('configurationItem', {}).get('address', {})
                        house_info = f"{address.get('location', '')}"

                        # Запрос для получения данных о счётчиках
                        configuration_item_id = personal_account.get('configurationItem', {}).get('id')
                        meters_url = f"https://nvs.domopult.ru/api/api/clients/meters/for-item/{configuration_item_id}"
                        meters_response = requests.get(meters_url, headers=headers)

                        if meters_response.status_code == 200:
                            meters_data = meters_response.json()
                            meters_info = ""
                            for meter in meters_data:
                                meter_type = meter.get('meter', {}).get('type', 'Неизвестный тип')
                                meter_number = meter.get('meter', {}).get('number', 'Неизвестный номер')
                                last_value = meter.get('meter', {}).get('lastValue', {}).get('total', {}).get('displayValue', 'Нет данных')
                                meters_info += f"<b>{meter_type}:</b> {meter_number} - Последнее показание: {last_value}\n"
                        else:
                            meters_info = "Не удалось получить данные о счётчиках."

                        # Формируем сообщение
                        welcome_message = f"<b>👋 Добро пожаловать в личный кабинет, {first_name}!</b>\n\n"
                        account_info_message = f"<b>🧾 Лицевой счёт:</b> {account_number}\n<b>💸 Баланс счёта:</b> {balance} ₽\n<b>🏠 Помещение:</b> {house_info}\n\n"
                        meters_message = f"<b>📊 Показания счётчиков:</b>\n{meters_info}\n"

                        # Создаем инлайн-кнопки
                        keyboard = [
                            [InlineKeyboardButton("💸 Пополнить баланс", callback_data='top_up_balance')],
                            [InlineKeyboardButton("📋 Квитанции", callback_data='download_receipt')],
                            [InlineKeyboardButton("🧭 Счётчики", callback_data='counters')],
                            [InlineKeyboardButton("⚙️ Подробная информация", callback_data='detailed_info')]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)

                        if update.message:
                            await update.message.reply_text(welcome_message + account_info_message + meters_message, parse_mode='HTML', reply_markup=reply_markup)
                        elif update.callback_query:
                            await update.callback_query.answer()
                            await update.callback_query.edit_message_text(welcome_message + account_info_message + meters_message, parse_mode='HTML', reply_markup=reply_markup)
                    else:
                        error_message = f"<b>❌ Ошибка при получении информации о счете.</b>\n├ Статус: {response.status_code}\n└ Сообщение: {response.text}"
                        if update.message:
                            await update.message.reply_text(error_message, parse_mode='HTML')
                        elif update.callback_query:
                            await update.callback_query.answer()
                            await update.callback_query.edit_message_text(error_message, parse_mode='HTML')
                else:
                    if update.message:
                        await update.message.reply_text(
                            "*❌ Не удалось найти идентификатор личного счета.*", parse_mode='MARKDOWN'
                        )
                    elif update.callback_query:
                        await update.callback_query.answer()
                        await update.callback_query.edit_message_text(
                            "*❌ Не удалось найти идентификатор личного счета.*", parse_mode='MARKDOWN'
                        )
            else:
                if update.message:
                    await update.message.reply_text(
                        "*❌ Нет данных о клиенте.*", parse_mode='MARKDOWN'
                    )
                elif update.callback_query:
                    await update.callback_query.answer()
                    await update.callback_query.edit_message_text(
                        "*❌ Нет данных о клиенте.*", parse_mode='MARKDOWN'
                    )
        elif response.status_code == 401:
            if update.message:
                await update.message.reply_text(
                    "*❌ Токен истёк.*\n└ Пожалуйста, пройдите процесс авторизации заново.", parse_mode='MARKDOWN'
                )
                delete_token(user_id)
            elif update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(
                    "*❌ Токен истёк.*\n└ Пожалуйста, пройдите процесс авторизации заново.", parse_mode='MARKDOWN'
                )
                delete_token(user_id)
        else:
            error_message = f"<b>❌ Ошибка при получении информации о клиенте.</b>\n├ Статус: {response.status_code}\n└ Сообщение: {response.text}"
            if update.message:
                await update.message.reply_text(error_message, parse_mode='HTML')
            elif update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(error_message, parse_mode='HTML')
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ошибка при получении информации о счёте: {e}")
        if update.message:
            await update.message.reply_text(
                "<b>❌ Произошла ошибка при обработке запроса.</b>\n└ Пожалуйста, попробуйте снова.", parse_mode='HTML'
            )
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                "<b>❌ Произошла ошибка при обработке запроса.</b>\n└ Пожалуйста, попробуйте снова.", parse_mode='HTML'
            )

async def top_up_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data='start')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Здесь можно добавить логику для пополнения баланса
    await query.edit_message_text(text="*⚙️ Разработка*\n└ Сейчас эта функция недоступна, попробуйте зайти сюда позже.", parse_mode='MARKDOWN', reply_markup=reply_markup)

async def detailed_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = context.user_data.get('account_data')
    if data:
        formatted_data = parse_and_format_data(data)
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data='start')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"<pre>{formatted_data}</pre>", 
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text(
            text="❌ Данные не найдены. Пожалуйста, попробуйте позже.", 
            parse_mode='HTML'
        )

async def ask_for_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if update.message:
        await update.message.reply_text("*✨ Квитанции*\n└ Пожалуйста, введите год для получения квитанции:", parse_mode='MARKDOWN')
    elif update.callback_query:
        await update.callback_query.message.reply_text("*✨ Квитанции*\n└ Пожалуйста, введите год для получения квитанции:", parse_mode='MARKDOWN')
    return SELECT_YEAR

async def handle_year_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_year = update.message.text
    if not selected_year.isdigit() or len(selected_year) != 4:
        await update.message.reply_text("*✨ Квитанции\n*└ Пожалуйста, введите корректный год (например, 2023):", parse_mode='MARKDOWN')
        return SELECT_YEAR
    context.user_data['selected_year'] = selected_year
    return await ask_for_month(update, context)

async def ask_for_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("*✨ Квитанции\n*└ Пожалуйста, введите месяц для получения квитанции (например, 01 для января):", parse_mode='MARKDOWN')
    elif update.callback_query:
        await update.callback_query.message.reply_text("*✨ Квитанции\n*└ Пожалуйста, введите месяц для получения квитанции (например, 01 для января):", parse_mode='MARKDOWN')
    return SELECT_MONTH

async def handle_month_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_month = update.message.text
    if not selected_month.isdigit() or len(selected_month) != 2 or not 1 <= int(selected_month) <= 12:
        await update.message.reply_text("*✨ Квитанции\n*└ Пожалуйста, введите корректный месяц (например, 01 для января):", parse_mode='MARKDOWN')
        return SELECT_MONTH
    context.user_data['selected_month'] = selected_month
    return await send_receipt(update, context)

async def send_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    auth_token = get_token(user_id)
    personal_account_id = get_personal_account_id(user_id)
    selected_year = context.user_data.get('selected_year')
    selected_month = context.user_data.get('selected_month')

    headers = {
        'X-Auth-Tenant-Token': f'{auth_token}',
        'Content-Type': 'application/json'
    }

    url = f"https://nvs.domopult.ru/api/api/personal_account/receipts_by_period/{personal_account_id}?date={selected_year}-{selected_month}-01&serviceType=UTILITIES"

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            receipt_file = response.content
            await context.bot.send_document(chat_id=update.effective_chat.id, document=receipt_file, filename=f"{selected_year}-{selected_month}-01.pdf")
        elif response.status_code == 400:
            await update.message.reply_text("*❌ Квитанции\n*└ Квитанция для выбранного периода недоступна, попробуйте позже.", parse_mode='MARKDOWN')
            return ConversationHandler.END
        else:
            await update.message.reply_text(f"<b>❌ Ошибка при получении квитанций.</b>\n├ Статус: {response.status_code}\n└ Сообщение: {response.text}", parse_mode='HTML')
    except requests.exceptions.RequestException as e:
        await update.message.reply_text("<b>❌ Произошла ошибка при обработке запроса.</b>\n└ Пожалуйста, попробуйте снова.", parse_mode='HTML')

    return ConversationHandler.END

async def show_counters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    auth_token = get_token(user_id)

    if not auth_token:
        await query.edit_message_text("*❌ Ваша авторизация не завершена.*\n└ Пожалуйста, пройдите процесс авторизации.", parse_mode='MARKDOWN')
        return ConversationHandler.END

    headers = {
        'X-Auth-Tenant-Token': f'{auth_token}',
        'Content-Type': 'application/json'
    }

    # Получаем configurationItemId из контекста
    response = requests.get(CLIENTS_CONFIGURATION_ITEMS_URL, headers=headers)
    if response.status_code == 200:
        data = response.json()
        items = data.get('items', [])
        
        if items:
            # Предполагаем, что первый элемент в списке items содержит нужный id
            configuration_item_id = items[0].get('id')
        else:
            print("Нет элементов в ответе")
    else:
        print(f"Ошибка при запросе: {response.status_code}")

    if not configuration_item_id:
        await query.edit_message_text("*❌ Не удалось найти идентификатор конфигурационного элемента.*", parse_mode='MARKDOWN')
        return ConversationHandler.END

    meters_url = f"https://nvs.domopult.ru/api/api/clients/meters/for-item/{configuration_item_id}"
    meters_response = requests.get(meters_url, headers=headers)

    if meters_response.status_code == 200:
        meters_data = meters_response.json()
        meters_info = ""
        keyboard = []
        for meter in meters_data:
            meter_type = meter.get('meter', {}).get('type', 'Неизвестный тип')
            if meter_type in ['ColdWater', 'HotWater']:
                meter_number = meter.get('meter', {}).get('number', 'Неизвестный номер')
                last_value = meter.get('meter', {}).get('lastValue', {}).get('total', {}).get('displayValue', 'Нет данных')
                meters_info += f"<b>{meter_type}:</b> {meter_number} - Последнее, общее показание: {last_value}\n"
                keyboard.append([InlineKeyboardButton(f"⏱️ Внести показания для {meter_type}", callback_data=f"meter_{meter['meter']['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"<b>📊 Показания счётчиков:</b>\n{meters_info}", parse_mode='HTML', reply_markup=reply_markup)
        return SELECT_METER
    else:
        await query.edit_message_text("*❌ Не удалось получить данные о счётчиках.*", parse_mode='MARKDOWN')
        return ConversationHandler.END

async def select_meter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    meter_id = query.data.split('_')[1]
    context.user_data['selected_meter_id'] = meter_id

    await query.edit_message_text("*📊 Счётчики.*\n└ Пожалуйста, введите показания счётчика:")
    return INPUT_READING

async def input_reading(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    meter_id = context.user_data.get('selected_meter_id')
    reading = update.message.text

    if '.' not in reading:
        await update.message.reply_text("*❌ Счётчики.*\n└ Показания должны содержать точку. Пожалуйста, введите показания снова.")
        return SELECT_METER

    user_id = update.effective_user.id
    auth_token = get_token(user_id)

    headers = {
        'X-Auth-Tenant-Token': f'{auth_token}',
        'Content-Type': 'application/json'
    }

    payload = {
        "value1": user_input
    }

    response = requests.post(f"https://nvs.domopult.ru/api/api/clients/meters/{meter_id}/values?withOptionalCheck=true", headers=headers, json=payload)

    if response.status_code == 200:
        await update.message.reply_text("*✅ Счётчики.*\n└ Показания успешно внесены.")
    else:
        await update.message.reply_text("*❌ Счётчики.*\n└ Не удалось внести показания.", parse_mode='MARKDOWN')

    return ConversationHandler.END

def main() -> None:
    init_db()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_METHOD: [CallbackQueryHandler(choose_method)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password)],
            SMS_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sms_code)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_for_year, pattern='^download_receipt$')],
        states={
            SELECT_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_year_input)],
            SELECT_MONTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_month_input)],
        },
        fallbacks=[],
    )

    meter_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_counters, pattern='^counters$')],
        states={
            SELECT_METER: [CallbackQueryHandler(select_meter, pattern='^meter_')],
            INPUT_READING: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_reading)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conversation_handler)
    application.add_handler(conv_handler)
    application.add_handler(meter_handler)
    application.add_handler(CallbackQueryHandler(show_counters, pattern='^counters$'))
    application.add_handler(CallbackQueryHandler(detailed_info_handler, pattern='^detailed_info$'))
    application.add_handler(CallbackQueryHandler(start, pattern='^start$'))
    application.add_handler(CallbackQueryHandler(top_up_balance, pattern='^top_up_balance$'))

    application.run_polling()

if __name__ == '__main__':
    main()