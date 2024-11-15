# handlers/setup.py
from telegram.ext import CommandHandler, MessageHandler, filters
from .user_handlers import start, send_cv, my_id
from .admin_handlers import liste_questions, tag_all, offremploi
from .message_handlers import welcome_new_member, handle_message

async def setup_application(app):
    """Setup all handlers for the application"""
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    # app.add_handler(CommandHandler("question", ask_question))
    # app.add_handler(CommandHandler("liste_questions", liste_questions))
    app.add_handler(CommandHandler("sendcv", send_cv))
    app.add_handler(CommandHandler("myid", my_id))
    app.add_handler(CommandHandler("tagall", tag_all))
    app.add_handler(CommandHandler("offremploi", offremploi))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
