from quart import Quart, request, jsonify
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

# Initialize the Quart app
app = Quart(__name__)

# Global variable for application
application = None

async def init_application():
    """Initialize and configure the Telegram application"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("question", ask_question))
    app.add_handler(CommandHandler("liste_questions", liste_questions))
    app.add_handler(CommandHandler("sendcv", send_cv))
    app.add_handler(CommandHandler("myid", my_id))
    app.add_handler(CommandHandler("tagall", tag_all))
    app.add_handler(CommandHandler("offremploi", offremploi))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return app

@app.before_serving
async def startup():
    """Initialize the bot before the first request"""
    global application
    application = await init_application()

@app.route('/')
async def hello():
    return "Hello, World!"

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        try:
            # Parse the update
            json_data = await request.get_json(force=True)
            update = Update.de_json(json_data, application.bot)
            
            # Process the update
            await application.process_update(update)
            
            return jsonify({"status": "ok"})
        except Exception as e:
            logger.error(f"Error processing update: {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "method not allowed"}), 405

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
