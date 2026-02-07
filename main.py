import telebot
from telebot import TeleBot, types
from telebot.apihelper import ApiTelegramException
from dotenv import load_dotenv
import sqlite3
import logging
import sys
import os

load_dotenv(dotenv_path=os.path.join('TOKEN', '.env'))
Token = os.getenv("TELEGRAM_TOKEN")
Admin_ID = os.getenv("Admin_ID")

if not Token:
    print("❌ Ошибка: Token не установлен!")
    sys.exit(1)

if not Admin_ID:
    print("❌ Ошибка: Admin_ID не установлен!")
    sys.exit(1)

bot = TeleBot(Token)
ADMIN_ID = int(Admin_ID)


user_logger = logging.getLogger("Actions")
user_logger.setLevel(logging.INFO)

user_handler = logging.FileHandler("Actions.log")
user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
user_logger.addHandler(user_handler)
user_logger.addHandler(logging.StreamHandler())

error_logger = logging.getLogger("Error")
error_logger.setLevel(logging.ERROR)

error_handler = logging.FileHandler("Error.log")
error_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
error_logger.addHandler(error_handler)
error_logger.addHandler(logging.StreamHandler())

DB_PATH = "List_ID/ID.db"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def ensure_db():

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

start = types.ReplyKeyboardMarkup(one_time_keyboard=True)
start.add("/add", "/all", "/view", "/send_message", "/send_file", "/replace_name", "/replace_user", "/replace_tag", "/delete", "/clear_db")

variant = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
variant.add("1", "2")

def crash_bot():
    try:
        bot.send_message(ADMIN_ID, f"@pe_xa_6 Бота крашнули!")
    except:
        pass

def insert_data(data):

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("INSERT OR REPLACE INTO list(user_id, user, name, tag, phone) VALUES(?, ?, ?, ?, ?)", data)
        db.commit()

def delete_data(message, id):
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
        error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/delete")


@bot.message_handler(func=lambda message: message.from_user.id != ADMIN_ID)
def echo_message(message):
    user_id = int(f"{message.from_user.id}")
    username = message.from_user.username or ""
    user = str(f"@{username}") if username else ""
    name = str(f"{message.from_user.first_name}") if message.from_user.first_name else ""

    user_logger.info(f"ID: {message.from_user.id} | User: @{username} | Wrote: {message.text}")
    try:
        bot.send_message(ADMIN_ID, f"ID: {message.from_user.id}\nUser: @{username}\nWrote: {message.text}")
    except:
        pass

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM list WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

    if result and result[0] > 0:
        pass
    else:
        insert_data((user_id, user, name, "", ""))


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Выбери одну из команд:\n"
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


@bot.message_handler(commands=['add'])
def write_down(message):
    msg = bot.send_message(message.chat.id, "Напишите ID, которое хотите сохранить:")
    bot.register_next_step_handler(msg, write_id)

def write_id(message):
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введите ID в формате (цифры).\n/add")
    else:
        bot.send_message(message.chat.id, "Введите User который начинается с @:")
        bot.register_next_step_handler(message, write_user, int(user_id))

def write_user(message, user_id):
    user = message.text.strip()

    if user.startswith('@') and len(user) > 1:
        valid_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        if all(char in valid_chars for char in user[1:]):
            bot.send_message(message.chat.id, "Введите Name:")
            bot.register_next_step_handler(message, write_name, user_id, user)
            return

    bot.reply_to(message, "❌ Введите тег в формате (@User).\n/add")

def write_name(message, user_id, user):
    name = message.text.strip()
    bot.send_message(message.chat.id, "Введите Tag или - если нет:")
    bot.register_next_step_handler(message, write_tag, user_id, user, name)

def write_tag(message, user_id, user, name):
    tag = message.text.strip()

    bot.send_message(message.chat.id, "Введите номер телефона в формате (пример: +380XXXXXXXXX) или - если не знаете.")
    bot.register_next_step_handler(message, write_phone, user_id, user, name, tag)

def write_phone(message, user_id, user, name, tag):
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
            error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка\n/add")
        return

    bot.reply_to(message, "❌ Введите номер телефона в формате +380XXXXXXXXX или - если не знаете.")
    bot.register_next_step_handler(message, write_phone, user_id, user, name, tag)


@bot.message_handler(commands=['all'])
def view_all_id(message):
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list")
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"\nNumber: {row[0]}\nID: {row[1]},  User: {row[2]},  Name: {row[3]},  Tag: {row[4] if row[4] else '-'},  Phone: {row[5] if row[5] else '-'}" for row in res])
    else:
        response = "❔ Нет записей."

    bot.reply_to(message, response, reply_markup=start)


@bot.message_handler(commands=['view'])
def view_id(message):
    bot.reply_to(message, "Выберите критерий для просмотра записей:\n"
                          "1 - По User.\n"
                          "2 - По Name.\n", reply_markup=variant)
    bot.register_next_step_handler(message, view_user_name)

def view_user_name(message):
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
    user = message.text.strip()

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE user=?", (user,))
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  User: {row[2]},  Name: {row[3]},  Tag: {row[4] if row[4] else '-'},  Phone: {row[5] if row[5] else '-'}" for row in res])
    else:
        response = "❔ Нет записей на этот User."

    bot.reply_to(message, response, reply_markup=start)

def process_view_name(message):
    name = message.text.strip()

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE name=?", (name,))
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  User: {row[2]},  Name: {row[3]},  Tag: {row[4] if row[4] else '-'},  Phone: {row[5] if row[5] else '-'}" for row in res])
    else:
        response = "❔ Нет записей на этот Name."
    bot.reply_to(message, response, reply_markup=start)


@bot.message_handler(commands=['send_message'])
def setting_send_message(message):
    bot.reply_to(message, "Выберите критерий для отправки сообщения:\n"
                          "1 - Отправить всем.\n"
                          "2 - Отправить по ID.\n", reply_markup=variant)
    bot.register_next_step_handler(message, variant_send_message)

def variant_send_message(message):
    variant_choice = message.text

    if variant_choice == "1":
        bot.send_message(message.chat.id, "Введите сообщение, которое хотите отправить всем:")
        bot.register_next_step_handler(message, send_message_all)
    elif variant_choice == "2":
        bot.send_message(message.chat.id, "Все записаны ID.")

        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM list")
            res = cursor.fetchall()

        if res:
            response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  User: {row[2]},  Name: {row[3]},  Tag: {row[4] if row[4] else '-'},  Phone: {row[5] if row[5] else '-'}" for row in res])
            bot.send_message(message.chat.id, response)
            msg = bot.send_message(message.chat.id, "Выделите ID кому хотите отправить сообщение:")
            bot.register_next_step_handler(msg, setting_send_message_id)
        else:
            response = "❔ Нет записей."
            bot.send_message(message.chat.id, response, reply_markup=start)
    else:
        bot.reply_to(message, "❌ Неверный выбор.\n/send_message")

def send_message_all(message):
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
            if "bot was blocked by the user" in str(e):
                error_logger.error(f"Ошибка в работе бота из-за: {message.from_user.id}\nError: {e}\n", exc_info=True)
            else:
                error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        except Exception as e:
            error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)

    bot.send_message(message.chat.id, f"✅ Сообщение: {text}. Было отправлено: {sent}.", reply_markup=start)

def setting_send_message_id(message):
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
    text = message.text

    try:
        bot.send_message(user_id, f"Сообщение: {text}")
        bot.send_message(message.chat.id, f"✅ Сообщение: {text}\nБыл отправлен пользователю с ID: {user_id}", reply_markup=start)
    except telebot.apihelper.ApiTelegramException as e:
        if "bot was blocked by the user" in str(e):
            error_logger.error(f"Ошибка в работе бота из-за:: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Пользователь заблокировал бота: {user_id}\n/send_message")
        else:
            error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Другая ошибка\n/send_message")
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/send_message")


@bot.message_handler(commands=['send_file'])
def setting_send_file(message):
    bot.reply_to(message, "Выберите критерий для отправки файла:\n"
                          "1 - Отправить всем.\n"
                          "2 - Отправить по ID.\n", reply_markup=variant)
    bot.register_next_step_handler(message, variant_send_file)

def variant_send_file(message):
    variant_choice = message.text

    if variant_choice == "1":
        bot.send_message(message.chat.id, "Сбросьте файл, который хотите отправить всем:")
        bot.register_next_step_handler(message, send_file_all)
    elif variant_choice == "2":
        bot.send_message(message.chat.id, "Все записаны ID:")

        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM list")
            res = cursor.fetchall()

        if res:
            response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  User: {row[2]},  Name: {row[3]},  Tag: {row[4] if row[4] else '-'},  Phone: {row[5] if row[5] else '-'}" for row in res])
            bot.send_message(message.chat.id, response)
            msg = bot.send_message(message.chat.id, "Введите user ID кому хотите отправить файл:")
            bot.register_next_step_handler(msg, setting_send_file_id)
        else:
            response = "❔ Нет записей."
            bot.send_message(message.chat.id, response, reply_markup=start)
    else:
        bot.reply_to(message, "❌ Неверный выбор.\n/send_file")

def send_file_all(message):
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
                error_logger.error(f"Ошибка в работе бота из-за: {message.from_user.id}\nError: {e}\n", exc_info=True)
                bot.reply_to(message, f"❌ Пользователь заблокировал бота: {user_id}\n/send_file")
            else:
                error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
                bot.reply_to(message, f"❌ Другая ошибка\n/send_file")
        except Exception as e:
            error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка\n/send_file")

    bot.send_message(message.chat.id, f"✅ Файл был послан: {sent} пользователям.", reply_markup=start)

def setting_send_file_id(message):
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введите ID в формате (цифры).\n/send_file")
    else:
        bot.send_message(message.chat.id, "Сбросьте файл, который хотите отправить:")
        bot.register_next_step_handler(message, setting_send_file_file, int(user_id))

def setting_send_file_file(message, user_id):
    file = message.document

    if file is None:
        bot.reply_to(message, "❌ Не получен файл отправьте файл.\n/send_file")
        return

    try:
        bot.send_document(user_id, file.file_id)
        bot.send_message(message.chat.id, f"✅ Файл был отправлен пользователю с ID: {user_id}", reply_markup=start)
    except telebot.apihelper.ApiTelegramException as e:
        if "bot was blocked by the user" in str(e):
            error_logger.error(f"Ошибка в работе бота из-за: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Пользователь заблокировал бота: {user_id}\n/send_file")
        else:
            error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Другая ошибка\n/send_file")
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/send_file")


@bot.message_handler(commands=['replace_name'])
def replace(message):
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list")
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  User: {row[2]},  Name: {row[3]},  Tag: {row[4] if row[4] else '-'},  Phone: {row[5] if row[5] else '-'}" for row in res])
    else:
        response = "❔ Нет записей."
    bot.reply_to(message, response)

    bot.send_message(message.chat.id, "Введите Number кому хотите заменить Name:")
    bot.register_next_step_handler(message, setting_replace)

def setting_replace(message):
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
    name = message.text.strip()

    try:
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("UPDATE list SET name = ? WHERE id = ?", (name, id))
            db.commit()

        bot.send_message(message.chat.id, f"✅ Name успешно обновлен для Number {id}.", reply_markup=start)
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/replace_name")


@bot.message_handler(commands=['replace_user'])
def replace_user_cmd(message):
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list")
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]}, User: {row[2]}, Name: {row[3]}, Tag: {row[4] if row[4] else '-'}, Phone: {row[5] if row[5] else '-'}" for row in res])
    else:
        response = "❔ Нет записей."

    bot.reply_to(message, response)
    bot.send_message(message.chat.id, "Введите Number кому хотите заменить User:")
    bot.register_next_step_handler(message, setting_replace_user)

def setting_replace_user(message):
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
        error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/replace_user")


@bot.message_handler(commands=['replace_tag'])
def replace_tag_cmd(message):
    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list")
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]}, User: {row[2]}, Name: {row[3]}, Tag: {row[4] if row[4] else '-'}, Phone: {row[5] if row[5] else '-'}" for row in res])
    else:
        response = "❔ Нет записей."

    bot.reply_to(message, response)
    bot.send_message(message.chat.id, "Введите Number кому хотите заменить Tag:")
    bot.register_next_step_handler(message, setting_replace_tag)

def setting_replace_tag(message):
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
        error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/replace_tag")


@bot.message_handler(commands=['delete'])
def delete_entry(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ Вы не являетесь администратором и не можете использовать эту команду.", reply_markup=start)
        return

    with sqlite3.connect(DB_PATH) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list")
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  User: {row[2]},  Name: {row[3]},  Tag: {row[4] if row[4] else '-'},  Phone: {row[5] if row[5] else '-'}" for row in res])
        bot.reply_to(message, response)
        msg = bot.send_message(message.chat.id, "Введите Number записи для удаления:")
        bot.register_next_step_handler(msg, process_delete)
    else:
        response = "❔ Нет записей.\n/delete"
        bot.reply_to(message, response)

def process_delete(message):
    id = message.text.strip()

    if not id.isdigit():
        bot.reply_to(message, "❌ Введите число Number.\n/delete")
    else:
        try:
            delete_data(message, int(id))
        except Exception as e:
            error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка\n/delete")


@bot.message_handler(commands=['clear_db'])
def clear_db(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ Вы не являетесь администратором и не можете использовать эту команду.", reply_markup=start)
        return

    try:
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM list")
            db.commit()

        bot.reply_to(message, "✅ Вся база данных была очищена.", reply_markup=start)
    except Exception as e:
        error_logger.error(f"Ошибка в работе бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Ошибка\n/clear_db")


while True:
    try:
        print("🤖 Бот запущен...")
        bot.polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        crash_bot()
        error_logger.error(f"Ошибка в работе polling()\nError: {e}\n", exc_info=True)
