import asyncio
import logging
import signal
from datetime import datetime
from typing import Optional

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from handlers.admin_handlers import tag_all, offremploi
from handlers.user_handlers import UserCommandHandler
from handlers.message_handlers import welcome_new_member, handle_message
from config import (
    BOT_TOKEN,
    SUPABASE_URL,
    SUPABASE_KEY
)
from supabase import create_client, Client

# Configure logging with detailed format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BotApplication(Application):
    """Enhanced Application class with integrated service clients."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supabase: Optional[Client] = None
        self.start_time: datetime = datetime.now()

    @classmethod
    def builder(cls):
        return BotApplicationBuilder()

    async def shutdown(self) -> None:
        """Enhanced shutdown with proper cleanup of resources."""
        logger.info("Initiating graceful shutdown...")
        
        try:
            # Call parent shutdown
            await super().shutdown()
            logger.info("Application shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
            raise

class BotApplicationBuilder(Application.builder().__class__):
    """Enhanced application builder with additional configuration options."""
    
    def __init__(self):
        super().__init__()
        self._application_class = BotApplication
        self._supabase: Optional[Client] = None

    def with_supabase(self, client: Client):
        """Configure Supabase client."""
        self._supabase = client
        return self

    def build(self) -> BotApplication:
        """Build the application with all configured components."""
        app = super().build()
        app.supabase = self._supabase
        return app

async def initialize_application() -> BotApplication:
    """Initialize and configure the bot application with all required components."""
    try:
        # Initialize Supabase client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        # Build application with components
        application = BotApplication.builder()\
            .token(BOT_TOKEN)\
            .with_supabase(supabase)\
            .build()

        # Initialize handlers
        user_handler = UserCommandHandler(
            supabase_client=supabase
        )

        # Register command handlers
        application.add_handler(CommandHandler("start", user_handler.start))
        application.add_handler(CommandHandler("sendcv", user_handler.send_cv))
        application.add_handler(CommandHandler("myid", user_handler.my_id))
        application.add_handler(CallbackQueryHandler(user_handler.callback_handler))

        # Register admin handlers
        application.add_handler(CommandHandler("tagall", tag_all))
        application.add_handler(CommandHandler("offremploi", offremploi))

        # Register message handlers
        application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_new_member
        ))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))

        return application
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        raise

async def main():
    """Main entry point for the bot application."""
    try:
        # Initialize application
        application = await initialize_application()
        
        if not application:
            logger.error("Failed to create application. Exiting...")
            return

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(application.shutdown())
            )

        # Start the application
        await application.initialize()
        await application.start()
        logger.info("Bot started successfully")
        
        # Run the application
        await application.run_polling(
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}")
        raise
    finally:
        # Ensure proper shutdown
        await application.shutdown()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot encountered an error: {str(e)}")
        exit(1)
