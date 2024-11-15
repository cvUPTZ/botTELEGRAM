from telegram.ext import CommandHandler, MessageHandler, filters
from .user_handlers import start, send_cv, my_id
from .admin_handlers import liste_questions, tag_all, offremploi
from .message_handlers import welcome_new_member, handle_message

async def setup_application(app):
    """
    Setup all handlers for the application
    
    Args:
        app: The telegram application instance
    """
    try:
        # User command handlers
        user_handlers = [
            CommandHandler("start", start),
            CommandHandler("sendcv", send_cv),
            CommandHandler("myid", my_id),
        ]
        
        # Admin command handlers
        admin_handlers = [
            CommandHandler("tagall", tag_all),
            CommandHandler("offremploi", offremploi),
            # Commented out but preserved for future use
            # CommandHandler("liste_questions", liste_questions),
            # CommandHandler("question", ask_question),
        ]
        
        # Message handlers
        message_handlers = [
            MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        ]
        
        # Register all handlers
        for handler in user_handlers + admin_handlers + message_handlers:
            app.add_handler(handler)
            
        return app
        
    except Exception as e:
        # Log any errors during setup
        logging.error(f"Error setting up application handlers: {str(e)}", exc_info=True)
        raise
