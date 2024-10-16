import asyncio
import logging
import requests
from quart import Quart, request
from telegram import Update
from telegram.ext import Application, CommandHandler
from telegram.error import RetryAfter, TelegramError
from config import PORT, WEBHOOK_URL, BOT_TOKEN

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Quart(__name__)

# Initialize the Application
bot_app = Application.builder().token(BOT_TOKEN).build()

async def start(update, context):
    logger.info(f"Received /start command from user {update.effective_user.id}")
    try:
        await update.message.reply_text('Hello! I am your bot.')
        logger.info(f"Sent response to user {update.effective_user.id}")
    except TelegramError as e:
        logger.error(f"Error sending response to user {update.effective_user.id}: {str(e)}")

bot_app.add_handler(CommandHandler("start", start))

@app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        logger.info("Webhook received!")
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, bot_app.bot)
        logger.info(f"Update received: {update}")
        await bot_app.process_update(update)
        logger.info("Update processed successfully")
        return 'OK'
    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}")
        return 'Error', 500

@app.route('/')
async def index():
    return 'Hello, World!'

async def set_webhook_with_retry(max_retries=5, initial_delay=1):
    for attempt in range(max_retries):
        try:
            result = await bot_app.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook set to: {WEBHOOK_URL}")
            logger.info(f"Webhook setup result: {result}")
            return
        except RetryAfter as e:
            if attempt < max_retries - 1:
                delay = e.retry_after if hasattr(e, 'retry_after') else initial_delay * (2 ** attempt)
                logger.info(f"Retry after {delay} seconds (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Failed to set webhook after {max_retries} attempts")
                raise

@app.before_serving
async def startup():
    await set_webhook_with_retry()
    await bot_app.initialize()
    await bot_app.start()
    logger.info("Bot application initialized and started")

@app.after_serving
async def shutdown():
    await bot_app.stop()
    await bot_app.shutdown()
    logger.info("Bot application stopped and shut down")

def check_bot():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    response = requests.get(url)
    logger.info(f"Bot check response: {response.json()}")

if __name__ == '__main__':
    check_bot()
    app.run(host='0.0.0.0', port=PORT)
