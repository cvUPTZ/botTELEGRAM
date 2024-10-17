import logging
import signal
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN, PORT
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message
from dash import Dash, html
from flask import Flask
from threading import Event

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Dash app
dash_app = Dash(__name__)
dash_app.layout = html.Div("Hello from Dash!")

# Create a Flask server
server = Flask(__name__)

# Combine Dash and Flask
dash_app.server = server

def signal_handler(sig, frame):
    logger.info("Shutting down bot gracefully...")
    sys.exit(0)

def main() -> None:
    try:
        # Initialize the Telegram bot
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

        # Start the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error("Error starting bot", exc_info=True)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C

    # Run the Dash app and Telegram bot concurrently
    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', PORT or 3001, server, use_reloader=True, use_debugger=True)
