import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN, WEBHOOK_URL, PORT
from bot.handler import (
    start, ask_question, liste_questions, send_cv, my_id, 
    tag_all, welcome_new_member, handle_message
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create the application instance
app = Application.builder().token(BOT_TOKEN).build()

# Add handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("question", ask_question))
app.add_handler(CommandHandler("liste_questions", liste_questions))
app.add_handler(CommandHandler("sendcv", send_cv))
app.add_handler(CommandHandler("myid", my_id))
app.add_handler(CommandHandler("tagall", tag_all))
app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

def main():
    # Check if using webhook
    if WEBHOOK_URL:
        # Set up webhook
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
    else:
        # Run polling if webhook is not set
        app.run_polling()

if __name__ == '__main__':
    main()
