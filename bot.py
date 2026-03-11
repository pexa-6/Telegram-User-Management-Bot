import telebot
from telebot import TeleBot, types
from telebot.apihelper import ApiTelegramException
from dotenv import load_dotenv
import sqlite3
import logging
import sys
import os
import uuid
import math
import time


load_dotenv()

# Переменные окружения
Token = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
Admin_ID = os.getenv("Admin_ID")

if not Token:
    print("❌ Ошибка: Token не установлен!")
    sys.exit(1)

if not Admin_ID:
    print("❌ Ошибка: Admin_ID не установлен!")
    sys.exit(1)

# Инициализация бота и ADMIN_ID
bot = TeleBot(Token)
ADMIN = int(Admin_ID)

# -----------------------
# Логгирование
# -----------------------
os.makedirs("logs", exist_ok=True)

user_logger = logging.getLogger("Actions")
user_logger.setLevel(logging.INFO)

user_handler = logging.FileHandler("logs/Actions.log")
user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
user_logger.addHandler(user_handler)
user_logger.addHandler(logging.StreamHandler())

error_logger = logging.getLogger("Error")
error_logger.setLevel(logging.ERROR)

error_handler = logging.FileHandler("logs/Error.log")
error_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
error_logger.addHandler(error_handler)
error_logger.addHandler(logging.StreamHandler())

# -----------------------
# Настройки БД и пагинации
# -----------------------
DB_PATH = "database/user.db"

# Кол-во записей на страницу (изменяй, если надо)
PAGE_SIZE = 20

# Убедиться, что папка для БД есть
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def ensure_db():
    """
    Создаёт таблицу list, если её нет.
    Структура таблицы:
        id      INTEGER PRIMARY KEY AUTOINCREMENT
        user_id INTEGER UNIQUE
        user    TEXT
        name    TEXT
        tag     TEXT
        phone   TEXT
    """
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS list(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                user TEXT,
                name TEXT,
                tag TEXT,
                phone TEXT
            );
        """)
        db.commit()


ensure_db()

# Кнопки основного меню (ReplyKeyboard)
start = types.ReplyKeyboardMarkup(one_time_keyboard=True)
start.add("/add", "/all", "/view", "/send_message", "/send_file", "/replace_name", "/replace_user", "/replace_tag", "/delete", "/clear_db")

# Варианты выбора (используется для /view и /send_message и т.д.)
variant = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
variant.add("1", "2")


def crash_bot():
    """Попытка уведомить администратора при краше polling()."""
    try:
        bot.send_message(ADMIN, f"@pe_xa_6 Бота крашнули!")
    except:
        pass


# -----------------------
# Работа с БД (вставка / удаление)
# -----------------------
def insert_data(data):
    """
    Вставляет или заменяет запись по уникальному user_id.
    data — кортеж (user_id, user, name, tag, phone)
    Используется при автоматическом логировании входящих сообщений и при /add.
    """
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("INSERT OR REPLACE INTO list(user_id, user, name, tag, phone) VALUES(?, ?, ?, ?, ?)", data)
        db.commit()


def delete_data(message, id):
    """
    Удаление записи по Number (id).
    В случае успеха отправляет ответ пользователю.
    """
    try:
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM list WHERE id=?", (id,))
            result = cursor.fetchone()

            if result:
                cursor.execute("DELETE FROM list WHERE id=?", (id,))
                db.commit()
                bot.reply_to(message, "✅ Запись успешно удалена.")
            else:
                bot.reply_to(message, "❔ Такой Number не найден.")
    except Exception as e:
        # Защищённый доступ к message.from_user.id (на случай, если message нестандартный)
        error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id', 'unknown')}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/delete")


# -----------------------
# Пагинация (session-based)
# -----------------------
# PAGINATION_SESSIONS: token -> { where, where_val, count, pages, ts }
# Токен создаётся при каждом вызове send_paginated_list и живёт в памяти.
# Если сессия устарела — приходится вызвать команду заново.
PAGINATION_SESSIONS = {}


def create_pagination_session(where=None, where_val=None):
    """
    Создаёт сессию пагинации:
    - where: имя поля WHERE (например "user" или "name") или None для общего списка
    - where_val: значение для WHERE
    Возвращает токен сессии.
    """
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        if where and where_val is not None:
            # Поддерживаем фильтр по полю
            cursor.execute(f"SELECT COUNT(*) FROM list WHERE {where}=?", (where_val,))
        else:
            cursor.execute("SELECT COUNT(*) FROM list")
        total = cursor.fetchone()[0] or 0

    pages = max(1, math.ceil(total / PAGE_SIZE))
    token = uuid.uuid4().hex
    PAGINATION_SESSIONS[token] = {
        'where': where,
        'where_val': where_val,
        'count': total,
        'pages': pages,
        'ts': time.time()
    }
    return token


def cleanup_old_sessions(ttl_seconds=3600):
    """
    Очищает старые сессии (по умолчанию — старше часа).
    Вызывается перед созданием новой сессии.
    """
    now = time.time()
    keys = [k for k, v in PAGINATION_SESSIONS.items() if now - v.get('ts', 0) > ttl_seconds]
    for k in keys:
        del PAGINATION_SESSIONS[k]


def fetch_page_rows(token, page):
    """
    Возвращает (rows, total_pages) для заданного токена и номера страницы.
    rows — список кортежей из БД.
    page — 0-based.
    """
    sess = PAGINATION_SESSIONS.get(token)
    if not sess:
        return [], 0
    offset = page * PAGE_SIZE
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        if sess['where'] and sess['where_val'] is not None:
            # Фильтрованный запрос
            cursor.execute(
                f"SELECT * FROM list WHERE {sess['where']}=? ORDER BY id ASC LIMIT ? OFFSET ?",
                (sess['where_val'], PAGE_SIZE, offset)
            )
        else:
            cursor.execute("SELECT * FROM list ORDER BY id ASC LIMIT ? OFFSET ?", (PAGE_SIZE, offset))
        rows = cursor.fetchall()
    return rows, sess['pages']


def format_rows_text(rows, header_prefix=""):
    """
    Форматирует список строк для отправки в сообщении.
    header_prefix — опциональная строка, добавляемая перед списком.
    """
    if not rows:
        return "❔ Нет записей."
    lines = []
    for row in rows:
        number = row[0]
        uid = row[1]
        user = row[2] or "-"
        name = row[3] or "-"
        tag = row[4] or "-"
        phone = row[5] or "-"
        # Каждая запись в несколько строк для читабельности
        lines.append(f"Number: {number}\nID: {uid},  User: {user},  Name: {name},\nTag: {tag},  Phone: {phone}")
    return header_prefix + "\n\n".join(lines)


def build_pagination_markup(token, current_page, total_pages):
    """
    Строит InlineKeyboardMarkup для пагинации:
    [⬅️] [X/Y] [➡️]
    callback_data:
      - "pag|{token}|{page}" — переход на страницу
      - "nop|{token}" — заглушка (не делает ничего)
    """
    kb = types.InlineKeyboardMarkup()
    buttons = []

    if current_page > 0:
        buttons.append(types.InlineKeyboardButton("⬅️", callback_data=f"pag|{token}|{current_page-1}"))
    else:
        # Заглушка вместо неактивной кнопки (чтобы верстка не скакала)
        buttons.append(types.InlineKeyboardButton(" ", callback_data=f"nop|{token}"))

    # Показываем текущую страницу и общее число страниц
    buttons.append(types.InlineKeyboardButton(f"{current_page+1}/{total_pages}", callback_data=f"nop|{token}"))

    if current_page < total_pages - 1:
        buttons.append(types.InlineKeyboardButton("➡️", callback_data=f"pag|{token}|{current_page+1}"))
    else:
        buttons.append(types.InlineKeyboardButton(" ", callback_data=f"nop|{token}"))

    kb.row(*buttons)
    return kb


def send_paginated_list(chat_id, where=None, where_val=None, header_prefix=""):
    """
    Создаёт сессию и отправляет первую страницу списка в чат.
    Возвращает (sent_message, token) — если нужно.
    """
    cleanup_old_sessions()
    token = create_pagination_session(where, where_val)
    rows, pages = fetch_page_rows(token, 0)
    text = format_rows_text(rows, header_prefix=header_prefix)
    markup = build_pagination_markup(token, 0, pages)
    try:
        sent = bot.send_message(chat_id, text, reply_markup=markup)
        return sent, token
    except Exception as e:
        # В случае ошибок логируем и отправляем без inline-кнопок
        error_logger.error(f"Ошибка при отправке paginated list: {e}", exc_info=True)
        sent = bot.send_message(chat_id, text)
        return sent, token


# -----------------------
# Обработка callback'ов от inline-кнопок пагинации
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data and (call.data.startswith("pag|") or call.data.startswith("nop|")))
def handle_pagination(call):
    """
    Обработка нажатий на кнопки пагинации.
    Ожидает callback_data в формате "pag|{token}|{page}".
    Если сессия устарела — возвращает уведомление об ошибке.
    """
    try:
        data = call.data
        parts = data.split("|")
        if parts[0] == "nop":
            # Ничего не делаем — просто подтверждаем callback
            try:
                bot.answer_callback_query(call.id)
            except:
                pass
            return

        token = parts[1]
        try:
            page = int(parts[2])
        except:
            page = 0

        sess = PAGINATION_SESSIONS.get(token)
        if not sess:
            # Сессия недействительна — просим пользователя вызвать команду заново
            try:
                bot.answer_callback_query(call.id, "❗️ Сессия устарела. Выполните команду снова.", show_alert=True)
            except:
                pass
            return

        rows, pages = fetch_page_rows(token, page)
        text = format_rows_text(rows)
        markup = build_pagination_markup(token, page, pages)

        try:
            # Пытаемся отредактировать существующее сообщение (экономим чат)
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        except Exception as e:
            # Если edit_message_text упал (например, старое сообщение или права) — отправляем новое
            try:
                bot.send_message(call.message.chat.id, text, reply_markup=markup)
            except Exception as send_exc:
                error_logger.error(f"Ошибка пагинации: {send_exc}", exc_info=True)
        try:
            bot.answer_callback_query(call.id)
        except:
            pass

    except Exception as e:
        error_logger.error(f"Ошибка пагинации: {e}", exc_info=True)


# -----------------------
# Обработка входящих сообщений (автоматическая запись пользователей)
# -----------------------
@bot.message_handler(func=lambda message: message.from_user.id != ADMIN)
def echo_message(message):
    """
    Хендлер для любых сообщений от НЕ-администратора:
    - логирует сообщение
    - посылает уведомление админу (если возможно)
    - добавляет пользователя в БД, если его там нет
    """
    user_id = int(f"{message.from_user.id}")
    username = message.from_user.username or ""
    user = str(f"@{username}") if username else ""
    name = str(f"{message.from_user.first_name}") if message.from_user.first_name else ""

    user_logger.info(f"ID: {message.from_user.id} | User: @{username} | Wrote: {message.text}")
    try:
        bot.send_message(ADMIN, f"ID: {message.from_user.id}\nUser: @{username}\nWrote: {message.text}")
    except:
        # Нельзя озадачивать бота падениями при уведомлении админа
        pass

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM list WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

    if result and result[0] > 0:
        # Уже есть в БД
        pass
    else:
        # Добавляем пользователя автоматически (tag и phone пустые)
        insert_data((user_id, user, name, "", ""))


# -----------------------
# Команды бота — реализация пользовательского интерфейса
# -----------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """/start — приветствие и меню команд."""
    bot.reply_to(message, "Выбери одну из команд:\n"
                          "\n"
                          "/add – Записать User.\n"
                          "/all – Все записаны Users.\n"
                          "/view – Просмотреть записи по определенным критериям.\n"
                          "/send_message – Отправить сообщение по определенным критериям.\n"
                          "/send_file – Отправить файл по определенным критериям.\n"
                          "/replace_name – Заменить Name по Number.\n"
                          "/replace_user – Заменить User по Number.\n"
                          "/replace_tag – Заменить Tag по Number.\n"
                          "/delete – Удалить запись по Number.\n"
                          "/clear_db – Очистить всю базу данных.", reply_markup=start)


# -----------------------
# Добавление записи (/add)
# -----------------------
@bot.message_handler(commands=['add'])
def write_down(message):
    """Запуск цепочки добавления: сначала просим ID."""
    msg = bot.send_message(message.chat.id, "Напишите ID, которое хотите сохранить:")
    bot.register_next_step_handler(msg, write_id)


def write_id(message):
    """Получаем ID (только цифры)."""
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введите ID в формате (цифры).\n/add")
    else:
        bot.send_message(message.chat.id, "Введите User который начинается с @:")
        bot.register_next_step_handler(message, write_user, int(user_id))


def write_user(message, user_id):
    """Получаем @user и проверяем валидность символов."""
    user = message.text.strip()

    if user.startswith('@') and len(user) > 1:
        valid_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        if all(char in valid_chars for char in user[1:]):
            bot.send_message(message.chat.id, "Введите Name:")
            bot.register_next_step_handler(message, write_name, user_id, user)
            return

    bot.reply_to(message, "❌ Введите тег в формате (@User).\n/add")


def write_name(message, user_id, user):
    """Получаем имя (name)."""
    name = message.text.strip()
    bot.send_message(message.chat.id, "Введите Tag или - если нет:")
    bot.register_next_step_handler(message, write_tag, user_id, user, name)


def write_tag(message, user_id, user, name):
    """Получаем tag (или '-' чтобы пропустить)."""
    tag = message.text.strip()
    bot.send_message(message.chat.id, "Введите номер телефона в формате (пример: +380XXXXXXXXX) или - если не знаете.")
    bot.register_next_step_handler(message, write_phone, user_id, user, name, tag)


def write_phone(message, user_id, user, name, tag):
    """Получаем телефон, проверяем формат (+...) или '-'."""
    phone = message.text.strip()

    is_skip = phone == "-"
    is_phone = phone.startswith('+') and len(phone) > 1 and phone[1:].isdigit()

    if is_skip or is_phone:
        if is_skip:
            phone = ""

        try:
            insert_data((user_id, user, name, tag, phone))
            bot.send_message(message.chat.id, "✅ Запись успешно добавлена.", reply_markup=start)
        except Exception as e:
            error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка\n/add")
        return

    bot.reply_to(message, "❌ Введите номер телефона в формате +380XXXXXXXXX или - если не знаете.")
    bot.register_next_step_handler(message, write_phone, user_id, user, name, tag)


# -----------------------
# Вывести полный (пагинированный) список (/all)
# -----------------------
@bot.message_handler(commands=['all'])
def view_all_id(message):
    """
    Показать список всех пользователей — с пагинацией.
    Если записей > PAGE_SIZE — пользователь увидит кнопку перехода по страницам.
    """
    send_paginated_list(message.chat.id)


# -----------------------
# Поиск и фильтрация (/view)
# -----------------------
@bot.message_handler(commands=['view'])
def view_id(message):
    """Выбор критерия для просмотра — по User или по Name."""
    bot.reply_to(message, "Выберите критерий для просмотра записей:\n"
                          "1 - По User.\n"
                          "2 - По Name.\n", reply_markup=variant)
    bot.register_next_step_handler(message, view_user_name)


def view_user_name(message):
    """Обработка выбора критерия просмотра."""
    variant_choice = message.text

    if variant_choice == "1":
        msg = bot.send_message(message.chat.id, "Введите User для просмотра записей:")
        bot.register_next_step_handler(msg, process_view_user_name)
    elif variant_choice == "2":
        msg = bot.send_message(message.chat.id, "Введите Name для просмотра записей:")
        bot.register_next_step_handler(msg, process_view_name)
    else:
        bot.reply_to(message, "❌ Неверный выбор.\n/view")


def process_view_user_name(message):
    """Фильтруем по user (username) и отправляем пагинированный результат."""
    user = message.text.strip()
    send_paginated_list(message.chat.id, where="user", where_val=user)


def process_view_name(message):
    """Фильтруем по name и отправляем пагинированный результат."""
    name = message.text.strip()
    send_paginated_list(message.chat.id, where="name", where_val=name)


# -----------------------
# Отправка сообщений (/send_message)
# -----------------------
@bot.message_handler(commands=['send_message'])
def setting_send_message(message):
    """Критерий отправки сообщения — всем или по ID."""
    bot.reply_to(message, "Выберите критерий для отправки сообщения:\n"
                          "1 - Отправить всем.\n"
                          "2 - Отправить по ID.\n", reply_markup=variant)
    bot.register_next_step_handler(message, variant_send_message)


def variant_send_message(message):
    """Обработка выбора варианта отправки."""
    variant_choice = message.text

    if variant_choice == "1":
        bot.send_message(message.chat.id, "Введите сообщение, которое хотите отправить всем:")
        bot.register_next_step_handler(message, send_message_all)
    elif variant_choice == "2":
        bot.send_message(message.chat.id, "Все записаны ID.")

        # Показываем пагинированный список с целью позволить админу скопировать ID
        send_paginated_list(message.chat.id)
        msg = bot.send_message(message.chat.id, "Выделите ID кому хотите отправить сообщение:", reply_markup=start)
        bot.register_next_step_handler(msg, setting_send_message_id)
    else:
        bot.reply_to(message, "❌ Неверный выбор.\n/send_message")


def send_message_all(message):
    """Режим: отправить текст ВСЕМ user_id из БД."""
    text = message.text

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT user_id FROM list")
        user_ids = [row[0] for row in cursor.fetchall()]

    sent = 0
    for user_id in user_ids:
        try:
            bot.send_message(f"{user_id}", f"Сообщение: {text}")
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            # Логируем, но не прерываем цикл
            if "bot was blocked by the user" in str(e):
                error_logger.error(f"Ошибка в работе бота из-за: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            else:
                error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        except Exception as e:
            error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)

    bot.send_message(message.chat.id, f"✅ Сообщение: {text}. Было отправлено: {sent}.", reply_markup=start)


def setting_send_message_id(message):
    """После того как админ ввёл ID — ждем текст сообщения для конкретного ID."""
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введите ID в формате (цифры).\n/send_message")
    else:
        try:
            bot.send_message(message.chat.id, "Введите сообщение, которое хотите отправить:")
            bot.register_next_step_handler(message, setting_send_message_text, int(user_id))
        except Exception as e:
            bot.reply_to(message, f"❌ Такого ID нет.\n/send_message")


def setting_send_message_text(message, user_id):
    """Отправляем текст конкретному ID."""
    text = message.text

    try:
        bot.send_message(user_id, f"Сообщение: {text}")
        bot.send_message(message.chat.id, f"✅ Сообщение: {text}\nБыл отправлен пользователю с ID: {user_id}", reply_markup=start)
    except telebot.apihelper.ApiTelegramException as e:
        if "bot was blocked by the user" in str(e):
            error_logger.error(f"Ошибка в работе бота из-за:: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Пользователь заблокировал бота: {user_id}\n/send_message")
        else:
            error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Другая ошибка\n/send_message")
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/send_message")


# -----------------------
# Отправка файлов (/send_file)
# -----------------------
@bot.message_handler(commands=['send_file'])
def setting_send_file(message):
    """Выбор отправки файла — всем или по ID."""
    bot.reply_to(message, "Выберите критерий для отправки файла:\n"
                          "1 - Отправить всем.\n"
                          "2 - Отправить по ID.\n", reply_markup=variant)
    bot.register_next_step_handler(message, variant_send_file)


def variant_send_file(message):
    """Обработка выбора варианта отправки файлов."""
    variant_choice = message.text

    if variant_choice == "1":
        bot.send_message(message.chat.id, "Сбросьте файл, который хотите отправить всем:")
        bot.register_next_step_handler(message, send_file_all)
    elif variant_choice == "2":
        bot.send_message(message.chat.id, "Все записаны ID:")
        send_paginated_list(message.chat.id)
        msg = bot.send_message(message.chat.id, "Введите user ID кому хотите отправить файл:", reply_markup=start)
        bot.register_next_step_handler(msg, setting_send_file_id)
    else:
        bot.reply_to(message, "❌ Неверный выбор.\n/send_file")


def send_file_all(message):
    """Отправляет присланный файл всем пользователям в БД."""
    file = message.document

    if file is None:
        bot.reply_to(message, "❌ Не получен файл отправьте файл.\n/send_file")
        return

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT user_id FROM list")
        user_ids = [row[0] for row in cursor.fetchall()]

    sent = 0
    for user_id in user_ids:
        try:
            bot.send_document(user_id, file.file_id)
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            if "bot was blocked by the user" in str(e):
                error_logger.error(f"Ошибка в работе бота из-за: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            else:
                error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        except Exception as e:
            error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)

    bot.send_message(message.chat.id, f"✅ Файл был послан: {sent} пользователям.", reply_markup=start)


def setting_send_file_id(message):
    """Получаем ID для отправки файла конкретному пользователю."""
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введите ID в формате (цифры).\n/send_file")
    else:
        bot.send_message(message.chat.id, "Сбросьте файл, который хотите отправить:")
        bot.register_next_step_handler(message, setting_send_file_file, int(user_id))


def setting_send_file_file(message, user_id):
    """Отправляем файл указанному ID."""
    file = message.document

    if file is None:
        bot.reply_to(message, "❌ Не получен файл отправьте файл.\n/send_file")
        return

    try:
        bot.send_document(user_id, file.file_id)
        bot.send_message(message.chat.id, f"✅ Файл был отправлен пользователю с ID: {user_id}", reply_markup=start)
    except telebot.apihelper.ApiTelegramException as e:
        if "bot was blocked by the user" in str(e):
            error_logger.error(f"Ошибка в работе бота из-за: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Пользователь заблокировал бота: {user_id}\n/send_file")
        else:
            error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Другая ошибка\n/send_file")
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/send_file")


# -----------------------
# Replace / Update handlers (replace_name / replace_user / replace_tag)
# -----------------------
@bot.message_handler(commands=['replace_name'])
def replace(message):
    """Показ пагинированного списка и запрос Number для замены name."""
    send_paginated_list(message.chat.id)
    bot.send_message(message.chat.id, "Введите Number кому хотите заменить Name:")
    bot.register_next_step_handler(message, setting_replace)


def setting_replace(message):
    """Проверка введённого Number и запрос нового name."""
    id = message.text.strip()

    if not id.isdigit():
        bot.reply_to(message, "❌ Введите Number в формате (цифры).\n/replace_name")
        return

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE id = ?", (id,))
        result = cursor.fetchone()

    if result:
        bot.send_message(message.chat.id, "Введите новый Name:")
        bot.register_next_step_handler(message, replace_name, id)
    else:
        bot.reply_to(message, "❔ Такого Number нет.\n/replace_name")


def replace_name(message, id):
    """Фактическая запись нового name в БД."""
    name = message.text.strip()

    try:
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("UPDATE list SET name = ? WHERE id = ?", (name, id))
            db.commit()

        bot.send_message(message.chat.id, f"✅ Name успешно обновлен для Number {id}.", reply_markup=start)
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/replace_name")


@bot.message_handler(commands=['replace_user'])
def replace_user_cmd(message):
    """Показ пагинации и запрос Number для замены user."""
    send_paginated_list(message.chat.id)
    bot.send_message(message.chat.id, "Введите Number кому хотите заменить User:")
    bot.register_next_step_handler(message, setting_replace_user)


def setting_replace_user(message):
    """Проверка Number и запрос нового @User."""
    id = message.text.strip()

    if not id.isdigit():
        bot.reply_to(message, "❌ Введите Number (цифры).\n/replace_user")
        return

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE id = ?", (id,))
        result = cursor.fetchone()

    if result:
        bot.send_message(message.chat.id, "Введите новый @User:")
        bot.register_next_step_handler(message, replace_user, id)
    else:
        bot.reply_to(message, "❔ Такого Number нет.\n/replace_user")


def replace_user(message, id):
    """Запись нового user (@username) в БД."""
    user = message.text.strip()

    if not user.startswith('@') or len(user) < 2:
        bot.reply_to(message, "❌ User должен начинаться с @ и быть не пустым.\n/replace_user")
        return

    try:
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("UPDATE list SET user = ? WHERE id = ?", (user, id))
            db.commit()

        bot.send_message(message.chat.id, f"✅ User обновлен для Number {id}", reply_markup=start)
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/replace_user")


@bot.message_handler(commands=['replace_tag'])
def replace_tag_cmd(message):
    """Показ пагинации и запрос Number для замены tag."""
    send_paginated_list(message.chat.id)
    bot.send_message(message.chat.id, "Введите Number кому хотите заменить Tag:")
    bot.register_next_step_handler(message, setting_replace_tag)


def setting_replace_tag(message):
    """Проверка Number и запрос нового tag (или '-' для удаления)."""
    id = message.text.strip()

    if not id.isdigit():
        bot.reply_to(message, "❌ Введите Number (цифры).\n/replace_tag")
        return

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE id = ?", (id,))
        result = cursor.fetchone()

    if result:
        bot.send_message(message.chat.id, "Введите новый Tag) или - если удалить:")
        bot.register_next_step_handler(message, replace_tag, id)
    else:
        bot.reply_to(message, "❔ Такого Number нет.\n/replace_tag")


def replace_tag(message, id):
    """Обновление/удаление поля tag."""
    tag = message.text.strip()
    if tag == "-":
        tag = ""
    try:
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("UPDATE list SET tag = ? WHERE id = ?", (tag, id))
            db.commit()

        bot.send_message(message.chat.id, f"✅ Tag обновлён для Number {id}", reply_markup=start)
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/replace_tag")


# -----------------------
# Удаление / Очистка БД
# -----------------------
@bot.message_handler(commands=['delete'])
def delete_entry(message):
    """Показ пагинации (для удобства) и запрос Number для удаления."""
    if int(message.from_user.id) != ADMIN:
        bot.reply_to(message, "❌ Вы не являетесь администратором и не можете использовать эту команду.", reply_markup=start)
        return

    send_paginated_list(message.chat.id)
    msg = bot.send_message(message.chat.id, "Введите Number записи для удаления:")
    bot.register_next_step_handler(msg, process_delete)


def process_delete(message):
    """Фактическое удаление записи по Number."""
    id = message.text.strip()

    if not id.isdigit():
        bot.reply_to(message, "❌ Введите число Number.\n/delete")
    else:
        try:
            delete_data(message, int(id))
        except Exception as e:
            error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка\n/delete")


@bot.message_handler(commands=['clear_db'])
def clear_db(message):
    """Полная очистка таблицы list (только админ)."""
    if int(message.from_user.id) != ADMIN:
        bot.reply_to(message, "❌ Вы не являетесь администратором и не можете использовать эту команду.", reply_markup=start)
        return

    try:
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM list")
            db.commit()

        bot.reply_to(message, "✅ Вся база данных была очищена.", reply_markup=start)
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {getattr(message.from_user,'id','unknown')}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/clear_db")


# -----------------------
# Запуск polling()
# -----------------------
if __name__ == "__main__":
    while True:
        try:
            print("🤖 Бот запущен...")
            bot.polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            # Пытаемся уведомить админа, логируем и продолжаем попытки перезапуска
            crash_bot()
            error_logger.error(f"Ошибка в работе polling()\nError: {e}\n", exc_info=True)
            # Небольшая пауза перед повтором (если хочешь, можно добавить time.sleep)