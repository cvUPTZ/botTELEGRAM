import logging
import threading
import signal
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message
from dash import Dash, html  # Import necessary Dash components

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Dash app
app = Dash(__name__)

# Define a simple layout for your Dash app
app.layout = html.Div("Hello from Dash!")

# Function to run the Dash server
def run_dash():
    app.run_server(debug=True, port=8050, host='0.0.0.0')

def signal_handler(sig, frame):
    logger.info("Shutting down bot gracefully...")
    sys.exit(0)

def main() -> None:
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

        # Start the Dash server in a separate thread
        dash_thread = threading.Thread(target=run_dash)
        dash_thread.start()
        logger.info("Dash server started successfully.")

        # Start the bot in polling mode
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot started successfully in polling mode")
    except Exception as e:
        logger.error("Error starting bot", exc_info=True)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    main()
