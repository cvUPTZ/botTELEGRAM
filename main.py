import asyncio
import logging
import signal
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id, callback_handler
from handlers.message_handlers import welcome_new_member, handle_message
from config import BOT_TOKEN, LINKEDIN_CLIENT_ID, LINKEDIN_REDIRECT_URI, REDIS_URL, SUPABASE_URL, SUPABASE_KEY
import redis
from supabase import create_client, Client

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global variable to control the bot's running state
bot_running = True

def signal_handler(sig, frame):
    global bot_running
    logger.info("Shutting down gracefully...")
    bot_running = False

def create_application():
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("question", ask_question))
    application.add_handler(CommandHandler("liste_questions", liste_questions))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CommandHandler("tagall", tag_all))
    application.add_handler(CommandHandler("offremploi", offremploi))

    # Register callback handler
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application

async def run_telegram_bot():
    global bot_running
    try:
        application = create_application()
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

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(run_telegram_bot())
