from quart import Quart, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application
import logging
import os
import asyncio
from functools import wraps
from mangum import Mangum
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
        try:
            # Configure custom request parameters
            request = HTTPXRequest(
                connection_pool_size=8,
                connect_timeout=20.0,
                read_timeout=20.0,
                write_timeout=20.0,
                pool_timeout=3.0,
            )

            # Initialize bot with custom request parameters
            bot = Bot(token=BOT_TOKEN, request=request)
            await bot.initialize()
            
            # Create and initialize application with same request parameters
            application = (
                Application.builder()
                .token(BOT_TOKEN)
                .request(request)
                .build()
            )
            await application.initialize()
            
            # Set the bot instance
            application.bot = bot
            
            # Initialize handlers
            await setup_application(application)
            
            logger.info("Bot and application initialized successfully")
        except Exception as e:
            logger.error(f"Error during initialization: {str(e)}", exc_info=True)
            raise

def ensure_initialized():
    """Decorator to ensure bot is initialized"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            global application, bot
            if application is None or bot is None:
                await initialize()
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@app.before_serving
async def startup():
    """Initialize the bot before the first request"""
    await initialize()

@app.route('/', methods=['GET'])
@ensure_initialized()
async def home():
    """Health check endpoint"""
    return jsonify({"status": "alive", "message": "Bot is running"})

@app.route('/webhook', methods=['POST'])
@ensure_initialized()
async def webhook():
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        try:
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

# Create handler for AWS Lambda
asgi_handler = Mangum(app, lifespan="off")

def lambda_handler(event, context):
    """AWS Lambda handler"""
    return asgi_handler(event, context)

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 8080)))
