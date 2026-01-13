import telebot
from telebot import TeleBot, types
from dotenv import load_dotenv
from telebot.apihelper import ApiTelegramException
import sys
import os
import re
import sqlite3
import logging


load_dotenv(dotenv_path=os.path.join('TOKEN', '.env'))
Token = os.getenv("TELEGRAM_TOKEN")
Admin_ID = os.getenv("Admin_ID")

if not Token:
    print("❌ Помилка: Token не встановлений!")
    sys.exit(1)

if not Admin_ID:
    print("❌ Помилка: Admin_ID не встановлений!")
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


db = sqlite3.connect("list_ID/ID.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS list(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user TEXT,
        name TEXT
    );
""")

db.commit()
db.close()


start = types.ReplyKeyboardMarkup(one_time_keyboard=True)
start.add("/add", "/all", "/view_users", "/send_message", "/send_file", "/replace_name", "/delete", "/clear_db")

variant = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
variant.add("1", "2")


def crash_bot():
    bot.send_message(ADMIN_ID, f"@pe_xa_6 Бота крашнул!")


def insert_data(data):
    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("INSERT INTO list(user_id, user, name) VALUES(?, ?, ?)", data)
        db.commit()


def delete_data(message, id):
    try:
        with sqlite3.connect("list_ID/ID.db") as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM list WHERE id=?", (id,))
            result = cursor.fetchone()

        if result:
            cursor.execute("DELETE FROM list WHERE id=?", (id,))
            db.commit()
            bot.reply_to(message, "✅ Запис успішно видалено.")
        else:
            bot.reply_to(message, "❔ Такий Number не знайдено.")


    except Exception as e:
        error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Помилка: {e}\n/delete")


@bot.message_handler(func=lambda message: message.from_user.id != ADMIN_ID)
def echo_message(message):
    user_id = int(f"{message.from_user.id}")
    user = str(f"@{message.from_user.username}")
    name = str(f"{message.from_user.first_name}")
    user_logger.info(f"ID Користувач: {message.from_user.id} | user_name користоуча: @{message.from_user.username} | Написав: {message.text}")
    bot.send_message(ADMIN_ID, f"ID Користувач: {message.from_user.id}\nuser_name користоуча: @{message.from_user.username}\nНаписав: {message.text}")

    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM list WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

    if result[0] > 0:
        print()
    elif result[0] == 0:
        insert_data((user_id, user, name))


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Вибери одну з команд:\n"
                          "/add - Записати ID.\n"
                          "/view_users - Переглянути записи за певними критеріями.\n"
                          "/all - Всі записані ID.\n"
                          "/delete - Видалити запис за Number.\n"
                          "/send_message - Надіслати повідомлення за певними критеріями.\n"
                          "/send_file - Надіслати файл за певними критеріями.\n"
                          "/replace_name - Замінити name за Number.\n"
                          "/clear_db - Очистить всю базу даних.", reply_markup=start)


@bot.message_handler(commands=['add'])
def write_down(message):
    msg = bot.send_message(message.chat.id, "Напишіть user ID яке хочете зберегти:")
    bot.register_next_step_handler(msg, write_id)


def write_id(message):
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введіть user ID у форматі (цифрами).\n/add")
    else:
        bot.send_message(message.chat.id, "Введіть тег користовуча який починається з @:")
        bot.register_next_step_handler(message, write_user, int(user_id))


def write_user(message, user_id):
    user = message.text.strip()

    if user.startswith('@') and len(user) > 1:
        valid_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        if all(char in valid_chars for char in user[1:]):
            bot.send_message(message.chat.id, "Введіть name:")
            bot.register_next_step_handler(message, write_name, user_id, user)

    else:
        bot.reply_to(message, "❌ Введіть тег у форматі (@user_name).\n/add")


def write_name(message, user_id, user):
    name = message.text.strip()

    try:
        insert_data((user_id, user, name))
        bot.send_message(message.chat.id, "✅ Запис успішно додано.")

    except Exception as e:
        error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Помилка: {e}\n/add")


@bot.message_handler(commands=['all'])
def view_all_id(message):
    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list")
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  user: {row[2]},  name: {row[3]}" for row in res])
    else:
        response = "❔ Немає записів."

    bot.reply_to(message, response)


@bot.message_handler(commands=['view_users'])
def view_id(message):
    bot.reply_to(message, "Оберіть критерій для перегляду записів:\n"
                          "1 - За user_name.\n"
                          "2 - За name.\n", reply_markup=variant)
    bot.register_next_step_handler(message, view_user_name)


def view_user_name(message):
    variant = message.text

    if variant == "1":
        msg = bot.send_message(message.chat.id, "Введіть user_name для перегляду записів:")
        bot.register_next_step_handler(msg, process_view_user_name)
    elif variant == "2":
        msg = bot.send_message(message.chat.id, "Введіть name для перегляду записів:")
        bot.register_next_step_handler(msg, process_view_name)
    else:
        bot.reply_to(message, "❌ Невірний вибір.\n/view_users")


def process_view_user_name(message):
    user = message.text

    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE user=?", (user,))
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  user: {row[2]},  name: {row[3]}" for row in res])
    else:
        response = "❔ Немає записів на цей users name."

    bot.reply_to(message, response, reply_markup=start)


def process_view_name(message):
    name = message.text

    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE name=?", (name,))
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  user: {row[2]},  name: {row[3]}" for row in res])
    else:
        response = "❔ Немає записів на цей name."
    bot.reply_to(message, response, reply_markup=start)


@bot.message_handler(commands=['delete'])
def delete_entry(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ Ви не є адміністратором і не можете використовувати цю команду.")
    else:
        with sqlite3.connect("list_ID/ID.db") as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM list")
            res = cursor.fetchall()

        if res:
            response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  user: {row[2]},  name: {row[3]}" for row in res])
            bot.reply_to(message, response)
            msg = bot.send_message(message.chat.id, "Введіть Number запису для видалення:")
            bot.register_next_step_handler(msg, process_delete)
        else:
            response = "❔ Немає записів."
            bot.reply_to(message, response)


def process_delete(message):
    id = message.text.strip()

    if not id.isdigit():
        bot.reply_to(message, "❌ Введіть числом Number.\n/delete")
    else:

        try:
            delete_data(message, int(id))

        except Exception as e:
            error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Помилка: {e}\n/delete")


@bot.message_handler(commands=['send_message'])
def setting_send_message(message):
    bot.reply_to(message, "Оберіть критерій для надіслання повідомлення:\n"
                          "1 - Надіслати всім.\n"
                          "2 - Надіслати за ID.\n", reply_markup=variant)
    bot.register_next_step_handler(message, variant_send_message)


def variant_send_message(message):
    variant = message.text

    if variant == "1":
        bot.send_message(message.chat.id, "Введіть повідомлення яке хочете надіслати всім:")
        bot.register_next_step_handler(message, send_message_all)
    elif variant == "2":
        bot.send_message(message.chat.id, "Всі записані ID.")

        with sqlite3.connect("list_ID/ID.db") as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM list")
            res = cursor.fetchall()

        if res:
            response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  user: {row[2]},  name: {row[3]}" for row in res])
            bot.send_message(message.chat.id, response)
            msg = bot.send_message(message.chat.id, "Видіть user ID кому хочети надіслати повідомлення:", reply_markup=start)
            bot.register_next_step_handler(msg, setting_send_message_id)
        else:
            response = "❔ Немає записів."
            bot.send_message(message.chat.id, response, reply_markup=start)
    else:
        bot.reply_to(message, "❌ Невірний вибір.\n/send_message")


def send_message_all(message):
    text = message.text

    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT user_id FROM list")
        user_ids = [row[0] for row in cursor.fetchall()]

    for user_id in user_ids:

        try:
            bot.send_message(f"{user_id}", f"Повідомлення: {text}")
            bot.send_message(message.chat.id, f"✅ Повідомлення: {text}. Було надіслано всім.", reply_markup=start)

        except telebot.apihelper.ApiTelegramException as e:
            if "bot was blocked by the user" in str(e):
                error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
                bot.reply_to(message, f"❌ Користувач заблокував бота: {user_id}\n/send_message")
            else:
                error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
                bot.reply_to(message, f"❌ Інша помилка: {e}\n/send_message")

        except Exception as e:
            error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Помилка: {e}\n/send_message")


def setting_send_message_id(message):
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введіть user ID у форматі (цифрами).\n/send_message")
    else:
        try:
            bot.send_message(message.chat.id, "Введіть повідомлення яке хочети надіслати:")
            bot.register_next_step_handler(message, setting_send_message_text, int(user_id))

        except:
            bot.reply_to(message, f"❌ Такого user ID немає.\n/send_message")


def setting_send_message_text(message, user_id):
    text = message.text

    try:
        bot.send_message(user_id, f"Повідомлення: {text}")
        bot.send_message(message.chat.id, f"Повідомлення: {text}\nБуло відправлено користувачу з ID: {user_id}")

    except telebot.apihelper.ApiTelegramException as e:
        if "bot was blocked by the user" in str(e):
            error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Користувач заблокував бота: {user_id}\n/send_message")
        else:
            error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Інша помилка: {e}\n/send_message")

    except Exception as e:
        error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Помилка: {e}\n/send_message")


@bot.message_handler(commands=['send_file'])
def setting_send_file(message):
    bot.reply_to(message, "Оберіть критерій для надіслання файла:\n"
                          "1 - Надіслати всім.\n"
                          "2 - Надіслати за ID.\n", reply_markup=variant)
    bot.register_next_step_handler(message, variant_send_file)


def variant_send_file(message):
    variant = message.text

    if variant == "1":
        bot.send_message(message.chat.id, "Скиньте файл який хочете надіслати всім:")
        bot.register_next_step_handler(message, send_file_all)
    elif variant == "2":
        bot.send_message(message.chat.id, "Всі записані ID:")

        with sqlite3.connect("list_ID/ID.db") as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM list")
            res = cursor.fetchall()

        if res:
            response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  user: {row[2]},  name: {row[3]}" for row in res])
            bot.send_message(message.chat.id, response)
            msg = bot.send_message(message.chat.id, "Введіть user ID кому хочете надіслати файл:", reply_markup=start)
            bot.register_next_step_handler(msg, setting_send_file_id)
        else:
            response = "❔ Немає записів."
            bot.send_message(message.chat.id, response, reply_markup=start)
    else:
        bot.reply_to(message, "❌ Невірний вибір.\n/send_file")


def send_file_all(message):
    file = message.document

    if file is None:
        bot.reply_to(message, "❌ Не отримано файл cкиньте файл.\n/send_file")

    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT user_id FROM list")
        user_ids = [row[0] for row in cursor.fetchall()]

    for user_id in user_ids:

        try:
            bot.send_document(user_id, file.file_id)
            bot.send_message(message.chat.id, "✅ Файл був надісланий всім.")

        except telebot.apihelper.ApiTelegramException as e:
            if "bot was blocked by the user" in str(e):
                error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
                bot.reply_to(message, f"❌ Користувач заблокував бота: {user_id}\n/send_file")
            else:
                error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
                bot.reply_to(message, f"❌ Інша помилка: {e}\n/send_file")

        except Exception as e:
            error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Помилка: {e}\n/send_file")


def setting_send_file_id(message):
    user_id = message.text.strip()

    if not user_id.isdigit():
        bot.reply_to(message, "❌ Введіть user ID у форматі (цифрами).\n/send_file")
    else:
        bot.send_message(message.chat.id, "Скиньте файл який хочете надіслати:")
        bot.register_next_step_handler(message, setting_send_file_file, int(user_id))


def setting_send_file_file(message, user_id):
    file = message.document

    if file is None:
        bot.reply_to(message, "❌ Не отримано файл cкиньте файл.\n/send_file")

    try:
        bot.send_document(user_id, file.file_id)
        bot.send_message(message.chat.id, f"Файл був надісланий користувачу з ID: {user_id}")

    except telebot.apihelper.ApiTelegramException as e:
        if "bot was blocked by the user" in str(e):
            error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Користувач заблокував бота: {user_id}\n/send_file")
        else:
            error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
            bot.reply_to(message, f"❌ Інша помилка: {e}\n/send_file")

    except Exception as e:
        error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Помилка: {e}\n/send_file")


@bot.message_handler(commands=['replace_name'])
def replace(message):
    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list")
        res = cursor.fetchall()

    if res:
        response = '\n'.join([f"Number: {row[0]}\nID: {row[1]},  user: {row[2]},  name: {row[3]}" for row in res])
    else:
        response = "❔ Немає записів."
    bot.reply_to(message, response)

    bot.send_message(message.chat.id, "Введіть Number кому хочети замінити name:")
    bot.register_next_step_handler(message, setting_replace)


def setting_replace(message):
    id = message.text.strip()

    if not id.isdigit():
        bot.reply_to(message, "❌ Введіть Number у форматі (цифрами).\n/replace_name")
        return

    with sqlite3.connect("list_ID/ID.db") as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM list WHERE id = ?", (id,))
        result = cursor.fetchone()

    if result:
        bot.send_message(message.chat.id, "Введіть новий name:")
        bot.register_next_step_handler(message, replace_name, id)
    else:
        bot.reply_to(message, "❔ Такого Number немає.")


def replace_name(message, id):
    name = message.text

    try:
        with sqlite3.connect("list_ID/ID.db") as db:
            cursor = db.cursor()
            cursor.execute("UPDATE list SET name = ? WHERE id = ?", (name, id))
            db.commit()

        bot.send_message(message.chat.id, f"✅ name успішно оновлено для Number {id}.")

    except Exception as e:
        error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Помилка: {e}\n/replace_name")


@bot.message_handler(commands=['clear_db'])
def clear_db(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ Ви не є адміністратором і не можете використовувати цю команду.")

    try:
        with sqlite3.connect("list_ID/ID.db") as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM list")
            db.commit()

        bot.reply_to(message, "✅ Вся база даних була очищена.")

    except Exception as e:
        error_logger.error(f"Помилка в роботі бота через: {message.from_user.id}\nError: {e}\n", exc_info=True)
        bot.reply_to(message, f"❌ Помилка: {e}\n/clear_db")


while True:
    try:
        print("🤖 Бот запущений...")
        bot.polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        crash_bot()
        error_logger.error(f"Помилка в роботі polling()\nError: {e}\n", exc_info=True)