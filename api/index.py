# index.py
from quart import Quart, request, jsonify
from telegram import Update
from telegram.ext import Application
import logging
import os
from handlers.setup import setup_application
from config import BOT_TOKEN

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

@app.before_serving
async def startup():
    """Initialize the bot before the first request"""
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    await setup_application(application)

@app.route('/', methods=['GET'])
async def home():
    """Health check endpoint"""
    return jsonify({"status": "alive", "message": "Bot is running"})

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        try:
            # Parse the update
            json_data = await request.get_json()
            update = Update.de_json(json_data, application.bot)
            
            # Process the update
            await application.process_update(update)
            return jsonify({"status": "ok"})
            
        except Exception as e:
            logger.error(f"Error processing update: {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "method not allowed"}), 405

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 8080)))
