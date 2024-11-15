from quart import Quart, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application
from telegram.request import HTTPXRequest
import logging
import os
import asyncio
from functools import wraps
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

# Global variables with proper typing
application: Application | None = None
bot: Bot | None = None

# Custom request parameters for better performance
REQUEST_KWARGS = {
    "connection_pool_size": 8,
    "connect_timeout": 20.0,
    "read_timeout": 20.0,
    "write_timeout": 20.0,
    "pool_timeout": 3.0,
}

async def initialize() -> None:
    """Initialize the bot and application"""
    global application, bot
    if application is None:
        try:
            # Configure custom request parameters
            request = HTTPXRequest(**REQUEST_KWARGS)

            # Initialize bot with custom request parameters
            bot = Bot(token=BOT_TOKEN, request=request)
            await bot.initialize()
            
            # Create and initialize application
            application = (
                Application.builder()
                .token(BOT_TOKEN)
                .request(request)
                .build()
            )
            await application.initialize()
            application.bot = bot
            
            # Setup handlers
            await setup_application(application)
            
            logger.info("Bot and application initialized successfully")
        except Exception as e:
            logger.error(f"Error during initialization: {str(e)}", exc_info=True)
            raise

def ensure_initialized(f):
    """Decorator to ensure bot is initialized"""
    @wraps(f)
    async def wrapper(*args, **kwargs):
        if application is None or bot is None:
            await initialize()
        return await f(*args, **kwargs)
    return wrapper

@app.before_serving
async def startup() -> None:
    """Initialize the bot before the first request"""
    await initialize()

@app.route('/', methods=['GET'])
@ensure_initialized
async def home():
    """Health check endpoint"""
    try:
        return jsonify({
            "status": "alive",
            "message": "Bot is running",
            "bot_initialized": bot is not None,
            "application_initialized": application is not None
        })
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
@ensure_initialized
async def webhook():
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        try:
            # Get the request data
            json_data = await request.get_json()
            
            # Log the incoming update
            logger.info(f"Received update: {json_data}")
            
            # Ensure bot is initialized
            if bot is None or application is None:
                raise RuntimeError("Bot or application not initialized")
            
            # Parse and process the update
            update = Update.de_json(json_data, bot)
            await application.process_update(update)
            
            return jsonify({"status": "ok"})
            
        except Exception as e:
            logger.error(f"Error processing update: {str(e)}", exc_info=True)
            return jsonify({
                "status": "error",
                "message": str(e),
                "type": type(e).__name__
            }), 500
    
    return jsonify({"status": "method not allowed"}), 405

@app.errorhandler(Exception)
async def handle_exception(e):
    """Handle any unhandled exceptions"""
    logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    return jsonify({
        "status": "error",
        "message": "An internal error occurred",
        "type": type(e).__name__
    }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
