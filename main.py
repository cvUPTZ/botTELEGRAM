import json
import logging
import asyncio
from typing import Dict, Any, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from supabase import create_client
import redis

from handlers.user_handlers import UserCommandHandler
from config import (
    BOT_TOKEN,
    SUPABASE_URL,
    SUPABASE_KEY,
    REDIS_URL
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global application instance
application: Optional[Application] = None


async def create_application() -> Application:
    """Create and configure the application instance."""
    try:
        # Initialize clients
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        redis_client = redis.from_url(REDIS_URL) if REDIS_URL else None

        # Create application
        app = Application.builder().token(BOT_TOKEN).build()

        # Initialize handlers
        user_handler = UserCommandHandler(
            supabase_client=supabase,
            redis_client=redis_client
        )

        # Register command handlers
        app.add_handler(CommandHandler("start", user_handler.start))
        app.add_handler(CommandHandler("sendcv", user_handler.send_cv))
        app.add_handler(CommandHandler("myid", user_handler.my_id))
        app.add_handler(CallbackQueryHandler(user_handler.callback_handler))

        # Store clients in application context
        app.bot_data["supabase"] = supabase
        app.bot_data["redis"] = redis_client

        return app

    except Exception as e:
        logger.error(f"Failed to create application: {str(e)}")
        raise


async def initialize() -> None:
    """Initialize the application if not already initialized."""
    global application
    if application is None:
        application = await create_application()
        logger.info("Application initialized successfully")


async def process_update(event: Dict[str, Any]) -> Dict[str, Any]:
    """Process incoming update from Lambda event."""
    try:
        # Ensure application is initialized
        await initialize()

        if not application:
            raise ValueError("Application failed to initialize")

        # Parse update
        update = Update.de_json(json.loads(event["body"]), application.bot)
        
        # Process update
        await application.process_update(update)

        return {
            "statusCode": 200,
            "body": json.dumps({"status": "success"})
        }

    except Exception as e:
        logger.error(f"Error processing update: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e)
            })
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler function."""
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Process update asynchronously
        return asyncio.get_event_loop().run_until_complete(
            process_update(event)
        )

    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": "Internal server error"
            })
        }


# For local development
if __name__ == "__main__":
    async def run_polling():
        """Run the bot with polling (for local development)."""
        try:
            # Initialize application
            await initialize()
            if not application:
                raise ValueError("Application failed to initialize")

            # Start polling
            await application.start()
            await application.run_polling(drop_pending_updates=True)

        except Exception as e:
            logger.error(f"Error in polling: {str(e)}")
            raise
        finally:
            if application:
                await application.shutdown()

    try:
        asyncio.run(run_polling())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot encountered an error: {str(e)}")
        exit(1)
