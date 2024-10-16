import asyncio
import requests
from quart import Quart, request
from telegram import Update
from telegram.ext import Application, CommandHandler
from telegram.error import RetryAfter
from config import PORT, WEBHOOK_URL, BOT_TOKEN

app = Quart(__name__)

# Initialize the Application
bot_app = Application.builder().token(BOT_TOKEN).build()

async def start(update, context):
    await update.message.reply_text('Hello! I am your bot.')

bot_app.add_handler(CommandHandler("start", start))

@app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        print("Webhook received!")
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, bot_app.bot)
        print(f"Update received: {update}")
        await bot_app.process_update(update)
        return 'OK'
    except Exception as e:
        print(f"Error in webhook: {str(e)}")
        return 'Error', 500

@app.route('/')
async def index():
    return 'Hello, World!'

async def set_webhook_with_retry(max_retries=5, initial_delay=1):
    for attempt in range(max_retries):
        try:
            result = await bot_app.bot.set_webhook(url=WEBHOOK_URL)
            print(f"Webhook set to: {WEBHOOK_URL}")
            print(f"Webhook setup result: {result}")
            return
        except RetryAfter as e:
            if attempt < max_retries - 1:
                delay = e.retry_after if hasattr(e, 'retry_after') else initial_delay * (2 ** attempt)
                print(f"Retry after {delay} seconds (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                print(f"Failed to set webhook after {max_retries} attempts")
                raise

@app.before_serving
async def startup():
    await set_webhook_with_retry()
    await bot_app.initialize()
    await bot_app.start()

@app.after_serving
async def shutdown():
    await bot_app.stop()
    await bot_app.shutdown()

def check_bot():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    response = requests.get(url)
    print(f"Bot check response: {response.json()}")

if __name__ == '__main__':
    check_bot()
    app.run(host='0.0.0.0', port=PORT)
