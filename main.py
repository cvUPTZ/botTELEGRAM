import asyncio
import logging
import signal
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from handlers.admin_handlers import tag_all, offremploi
from handlers.user_handlers import UserCommandHandler
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
from utils.linkedin_utils import LinkedInConfig, LinkedInTokenManager, LinkedInVerificationManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class CustomApplication(Application):
    """Custom Application class with additional clients."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supabase = None
        self.redis_client = None
        self.linkedin_token_manager = None
        self.linkedin_verification_manager = None

    @classmethod
    def builder(cls):
        return CustomDefaultBuilder()

class CustomDefaultBuilder(Application.builder().__class__):
    def __init__(self):
        super().__init__()
        self._application_class = CustomApplication
        self._supabase = None
        self._redis_client = None
        self._linkedin_config = None

    def supabase_client(self, client: Client):
        self._supabase = client
        return self

    def redis_client(self, client: redis.Redis):
        self._redis_client = client
        return self

    def linkedin_config(self, config: LinkedInConfig):
        self._linkedin_config = config
        return self

    def build(self) -> CustomApplication:
        app = super().build()
        app.supabase = self._supabase
        app.redis_client = self._redis_client
        
        # Initialize LinkedIn managers
        app.linkedin_token_manager = LinkedInTokenManager(
            app.redis_client,
            self._linkedin_config
        )
        
        app.linkedin_verification_manager = LinkedInVerificationManager(
            app.redis_client,
            app.linkedin_token_manager,
            self._linkedin_config
        )
        
        return app

def create_application():
    """Create and configure the application with all handlers."""
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

        # Create application with all clients
        application = CustomApplication.builder()\
            .token(BOT_TOKEN)\
            .supabase_client(supabase)\
            .redis_client(redis_client)\
            .linkedin_config(linkedin_config)\
            .build()

        # Initialize UserCommandHandler with all managers
        user_handler = UserCommandHandler(
            redis_client=redis_client,
            supabase_client=supabase,
            linkedin_config=linkedin_config,
            linkedin_token_manager=application.linkedin_token_manager,
            linkedin_verification_manager=application.linkedin_verification_manager
        )

        # Add command handlers
        application.add_handler(CommandHandler("start", user_handler.start))
        application.add_handler(CommandHandler("sendcv", user_handler.send_cv))
        application.add_handler(CommandHandler("myid", user_handler.my_id))
        # Uncomment if needed
        # application.add_handler(CommandHandler("verify", user_handler.verify_linkedin))
        application.add_handler(CallbackQueryHandler(user_handler.callback_handler))

        # Add admin and message handlers
        application.add_handler(CommandHandler("tagall", tag_all))
        application.add_handler(CommandHandler("offremploi", offremploi))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        return application
    
    except Exception as e:
        logger.error(f"Error creating application: {str(e)}")
        raise

async def main():
    """Main entry point to run the application."""
    application = create_application()
    
    if not application:
        logger.error("Failed to create application. Exiting...")
        return

    # Graceful shutdown handling
    loop = asyncio.get_running_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(application.shutdown())
        )

    await application.initialize()
    await application.start()
    logger.info("Bot started successfully")
    await application.run_polling()
    await application.shutdown()
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Bot encountered an error: {str(e)}")
        exit(1)
