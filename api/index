import os
import logging
from quart import Quart
from dash import Dash, html
from telegram import Update
from telegram.ext import Application
from config import BOT_TOKEN
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Quart app
app = Quart(__name__)

# Initialize the Dash app
dash_app = Dash(__name__, server=app)
dash_app.layout = html.Div("Hello from Dash!")

# Add a route for the root URL (health check endpoint)
@app.route('/')
async def hello():
    return "Hello, World!"

# Function to run the Telegram bot
async def run_telegram_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    # Add your command and message handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("question", ask_question))
    application.add_handler(CommandHandler("liste_questions", liste_questions))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CommandHandler("tagall", tag_all))
    application.add_handler(CommandHandler("offremploi", offremploi))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await application.initialize()
    await application.start()

    logger.info("Telegram bot started successfully")

    # Keep the bot running
    while True:
        await asyncio.sleep(1)

# Entry point for Vercel
async def main(req):
    await run_telegram_bot()  # Start the bot in the background
    return await app(req)  # Handle incoming requests

if __name__ == "__main__":
    app.run()
