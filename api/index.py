# index.py
from quart import Quart, request, jsonify
from telegram import Update, Bot
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

# Global variables
application = None
bot = None

async def initialize():
    """Initialize the bot and application"""
    global application, bot
    if application is None:
        bot = Bot(token=BOT_TOKEN)
        application = Application.builder().token(BOT_TOKEN).build()
        await application.initialize()  # Initialize the application
        await setup_application(application)  # Setup handlers
        logger.info("Bot initialized successfully")

@app.before_serving
async def startup():
    """Initialize the bot before the first request"""
    await initialize()

@app.route('/', methods=['GET'])
async def home():
    """Health check endpoint"""
    return jsonify({"status": "alive", "message": "Bot is running"})

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        try:
            # Ensure application is initialized
            if application is None:
                await initialize()

            # Parse the update
            json_data = await request.get_json()
            update = Update.de_json(json_data, bot)
            
            # Process the update
            await application.process_update(update)
            return jsonify({"status": "ok"})
            
        except Exception as e:
            logger.error(f"Error processing update: {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "method not allowed"}), 405

# Create folder for lambda function
def handler(event, context):
    """AWS Lambda handler"""
    return app.handle_lambda(event, context)

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 8080)))
