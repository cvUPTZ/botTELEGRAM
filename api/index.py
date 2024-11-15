from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message
import logging

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Flask app
app = Flask(__name__)

# Initialize the Telegram Application (Singleton)
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

@app.route('/')
def hello():
    return "Hello, World!"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        # Process the incoming update
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.create_task(application.process_update(update))
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # Initialize the Telegram Application
    application.run_polling(stop_signals=None)
    # Start the Flask app
    app.run(debug=True)
