import os
import telebot
import google.generativeai as genai
from telebot.types import Message
import base64
import httpx

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction="""Ти — асистент ювелірного магазину MINIMAL. 
Допомагаєш продавцям правильно вирішувати ситуації з гарантійними випадками та поверненнями.

ПРАВИЛА ГАРАНТІЇ:
- Гарантія діє 6 місяців з дати покупки
- Гарантія покриває: виробничі дефекти, випадіння каменів без механічного пошкодження
- Гарантія НЕ покриває: механічні пошкодження, сліди носіння, втрата виробу
- Для гарантії потрібна бірка або чек

ПРАВИЛА ПОВЕРНЕННЯ:
- Повернення можливе протягом 14 днів з дати покупки
- Виріб має бути без слідів носіння, з биркою
- Сережки поверненню НЕ підлягають (гігієнічні норми), окрім виробничого браку

ФОРМАТ ВІДПОВІДІ:
1. Коротко визнач ситуацію (гарантія / повернення / відмова)
2. Поясни чому (1-2 речення)
3. Дай продавцю конкретну фразу для клієнта
4. Якщо потрібні додаткові документи — вкажи які

Відповідай коротко, по справі, українською мовою."""
)

user_chats = {}
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_user_chat(user_id):
    if user_id not in user_chats:
        user_chats[user_id] = model.start_chat(history=[])
    return user_chats[user_id]

@bot.message_handler(commands=["start"])
def handle_start(message: Message):
    text = (
        "👋 Привіт! Я асистент магазину MINIMAL.\n\n"
        "Допомагаю вирішувати ситуації з:\n"
        "🔹 Гарантійними випадками\n"
        "🔹 Поверненнями\n"
        "🔹 Аналізом фото виробів\n\n"
        "Просто опиши ситуацію або надішли фото прикраси.\n\n"
        "📌 /new — почати нову розмову"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=["new"])
def handle_new(message: Message):
    user_id = message.from_user.id
    user_chats[user_id] = model.start_chat(history=[])
    bot.send_message(message.chat.id, "✅ Новий діалог розпочато. Опишіть ситуацію.")

@bot.message_handler(content_types=["text"])
def handle_text(message: Message):
    user_id = message.from_user.id
    bot.send_chat_action(message.chat.id, "typing")
    try:
        chat = get_user_chat(user_id)
        response = chat.send_message(message.text)
        bot.send_message(message.chat.id, response.text)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Помилка: {str(e)}")

@bot.message_handler(content_types=["photo"])
def handle_photo(message: Message):
    user_id = message.from_user.id
    bot.send_chat_action(message.chat.id, "typing")
    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        image_data = httpx.get(file_url).content
        caption = message.caption or "Проаналізуй цей виріб. Опиши стан, видимі дефекти, сліди носіння."
        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_data).decode("utf-8")
        }
        chat = get_user_chat(user_id)
        response = chat.send_message([caption, image_part])
        bot.send_message(message.chat.id, response.text)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Помилка при обробці фото: {str(e)}")

print("Бот запущено ✅")
bot.infinity_polling()
