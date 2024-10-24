# main.py
import asyncio
import logging
import signal
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from handlers.admin_handlers import tag_all, offremploi
from handlers.user_handlers import UserCommandHandler  # Import the class, not the individual functions
from handlers.message_handlers import welcome_new_member, handle_message
from config import (
    BOT_TOKEN, 
    REDIS_URL, 
    SUPABASE_URL, 
    SUPABASE_KEY,
    LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET,
    LINKEDIN_REDIRECT_URI,
    LINKEDIN_POST_URL,
    LINKEDIN_ACCESS_TOKEN,
    LINKEDIN_SCOPE,
    COMPANY_PAGE_ID,
    LINKEDIN_POST_ID
)
import redis
from supabase import create_client, Client
from utils.linkedin_utils import LinkedInConfig

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class CustomApplication(Application):
    """Custom Application class with Supabase client"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supabase = None
        self.redis_client = None

    @classmethod
    def builder(cls):
        """Override builder to return CustomDefaultBuilder"""
        return CustomDefaultBuilder()

class CustomDefaultBuilder(Application.builder().__class__):
    """Custom builder that creates CustomApplication instances"""
    def __init__(self):
        super().__init__()
        self._application_class = CustomApplication
        self._supabase = None
        self._redis_client = None

    def supabase_client(self, client: Client):
        """Set the Supabase client"""
        self._supabase = client
        return self

    def redis_client(self, client: redis.Redis):
        """Set the Redis client"""
        self._redis_client = client
        return self

    def build(self) -> CustomApplication:
        """Build the custom application with clients"""
        app = super().build()
        app.supabase = self._supabase
        app.redis_client = self._redis_client
        return app

def create_application():
    """Create and configure the application with all handlers"""
    try:
        # Initialize clients
        redis_client = redis.from_url(REDIS_URL)
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Create LinkedIn configuration
        linkedin_config = LinkedInConfig(
            client_id=LINKEDIN_CLIENT_ID,
            client_secret=LINKEDIN_CLIENT_SECRET,
            redirect_uri=LINKEDIN_REDIRECT_URI,
            post_url=LINKEDIN_POST_URL,
            access_token=LINKEDIN_ACCESS_TOKEN,
            scope=LINKEDIN_SCOPE,
            company_page_id=COMPANY_PAGE_ID,
            post_id=LINKEDIN_POST_ID
        )
        
        # Create application with clients
        application = CustomApplication.builder()\
            .token(BOT_TOKEN)\
            .supabase_client(supabase)\
            .redis_client(redis_client)\
            .build()

        # Instantiate UserCommandHandler with all required parameters
        user_handler = UserCommandHandler(
            redis_client=redis_client,
            supabase_client=supabase,
            linkedin_config=linkedin_config
        )

        # Add handlers from user commands
        application.add_handler(CommandHandler("start", user_handler.start))
        application.add_handler(CommandHandler("sendcv", user_handler.send_cv))
        application.add_handler(CommandHandler("myid", user_handler.my_id))
        application.add_handler(CallbackQueryHandler(user_handler.callback_handler))

        # Add admin and message handlers
        application.add_handler(CommandHandler("tagall", tag_all))
        application.add_handler(CommandHandler("offremploi", offremploi))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        return application
    
    except Exception as e:
        logger.error(f"Error creating application: {str(e)}")
        raise  # Re-raise the exception for better error tracking

async def main():
    """Main entry point to run the application"""
    try:
        application = create_application()

        if not application:
            logger.error("Failed to create application. Exiting...")
            return

        # Graceful shutdown on SIGINT or SIGTERM
        loop = asyncio.get_running_loop()
        for sig in [signal.SIGINT, signal.SIGTERM]:
            loop.add_signal_handler(
                sig, lambda: asyncio.create_task(application.shutdown())
            )

        # Start the application
        await application.initialize()  # Add this line
        await application.start()
        logger.info("Bot started successfully")

        # Run until stopped
        await application.run_polling()
        await application.shutdown()
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Bot encountered an error: {str(e)}")
        exit(1)  # Exit with error code
