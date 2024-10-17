import asyncio
import logging
import signal
import sys
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message
from dash import Dash, html
from quart import Quart
from hypercorn.asyncio import serve
from hypercorn.config import Config

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Dash app
dash_app = Dash(__name__)
dash_app.layout = html.Div("Hello from Dash!")

# Create a Quart server (asyncio-compatible Flask-like server)
server = Quart(__name__)
dash_app.server = server

# Add a route for the root URL (this also serves as a health check endpoint)
@server.route('/')
async def hello():
    return "Hello, World!"

# Configure Hypercorn
config = Config()
config.bind = [f"0.0.0.0:{os.environ.get('PORT', 10000)}"]  # Render sets PORT environment variable
config.use_reloader = False
config.workers = 1

# Global variable to control the bot's running state
bot_running = True

def signal_handler(sig, frame):
    global bot_running
    logger.info("Shutting down gracefully...")
    bot_running = False

async def run_dash():
    await serve(server, config)

async def run_telegram_bot():
    global bot_running
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
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
        
        # Start polling in a separate task
        polling_task = asyncio.create_task(
            application.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        )

        logger.info("Telegram bot started successfully")
        
        # Keep the bot running until bot_running is set to False
        while bot_running:
            await asyncio.sleep(1)

        # Proper shutdown
        logger.info("Stopping Telegram bot...")
        await polling_task
        await application.stop()
        await application.shutdown()
        
    except Exception as e:
        logger.error("Error running Telegram bot", exc_info=True)

async def main():
    dash_task = asyncio.create_task(run_dash())
    telegram_task = asyncio.create_task(run_telegram_bot())

    await asyncio.gather(dash_task, telegram_task)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())
