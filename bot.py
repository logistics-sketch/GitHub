import os
import telebot
import anthropic
from telebot.types import Message
import base64
import httpx

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
user_contexts = {}

SYSTEM_PROMPT = """Ти — асистент ювелірного магазину MINIMAL. Допомагаєш продавцям правильно вирішувати ситуації з гарантійними випадками та поверненнями.

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

def get_user_context(user_id):
    if user_id not in user_contexts:
        user_contexts[user_id] = []
    return user_contexts[user_id]

def add_to_context(user_id, role, content):
    user_contexts[user_id].append({"role": role, "content": content})
    if len(user_contexts[user_id]) > 10:
        user_contexts[user_id] = user_contexts[user_id][-10:]

@bot.message_handler(commands=["start"])
def handle_start(message: Message):
    text = ("👋 Привіт! Я асистент магазину MINIMAL.\n\nДопомагаю вирішувати ситуації з:\n🔹 Гарантійними випадками\n🔹 Поверненнями\n🔹 Аналізом фото виробів\n\nПросто опиши ситуацію або надішли фото прикраси.\n\n📌 /new — почати нову розмову")
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=["new"])
def handle_new(message: Message):
    user_id = message.from_user.id
    user_contexts[user_id] = []
    bot.send_message(message.chat.id, "✅ Новий діалог розпочато. Опишіть ситуацію.")

@bot.message_handler(content_types=["text"])
def handle_text(message: Message):
    user_id = message.from_user.id
    bot.send_chat_action(message.chat.id, "typing")
    add_to_context(user_id, "user", message.text)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=get_user_context(user_id),
        )
        reply = response.content[0].text
        add_to_context(user_id, "assistant", reply)
        bot.send_message(message.chat.id, reply)
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
        image_base64 = base64.standard_b64encode(image_data).decode("utf-8")
        caption = message.caption or "Проаналізуй цей виріб. Опиши стан, видимі дефекти, сліди носіння."
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}},
            {"type": "text", "text": caption},
        ]
        add_to_context(user_id, "user", content)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=get_user_context(user_id),
        )
        reply = response.content[0].text
        add_to_context(user_id, "assistant", reply)
        bot.send_message(message.chat.id, reply)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Помилка при обробці фото: {str(e)}")

print("Бот запущено ✅")
bot.infinity_polling()
