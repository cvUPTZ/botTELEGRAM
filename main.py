import asyncio
import logging
import signal
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, LINKEDIN_CLIENT_ID, LINKEDIN_REDIRECT_URI, REDIS_URL
import redis

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL)

# Global variable to control the bot's running state
bot_running = True

def signal_handler(sig, frame):
    global bot_running
    logger.info("Shutting down gracefully...")
    bot_running = False

# Handler functions
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /help to see available commands.")

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("What's your question?")

async def liste_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Here's a list of frequently asked questions...")

async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send your CV as a file.")

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Your Telegram ID is: {user_id}")

async def tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Implement the logic to tag all users in the group
    await update.message.reply_text("Tagging all users...")

async def offremploi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Here are the latest job offers...")

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        await update.message.reply_text(f"Welcome {new_member.first_name} to the group!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Implement general message handling logic
    await update.message.reply_text("I received your message.")

async def start_linkedin_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    auth_url = f"{LINKEDIN_REDIRECT_URI.replace('/linkedin-callback', '')}/start-linkedin-auth/{user_id}"
    keyboard = [[InlineKeyboardButton("Verify with LinkedIn", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Please click the button below to verify your LinkedIn profile:",
        reply_markup=reply_markup
    )

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
    application.add_handler(CommandHandler("verify_linkedin", start_linkedin_verification))
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
