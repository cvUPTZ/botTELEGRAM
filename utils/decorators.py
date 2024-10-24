from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_USER_IDS

def admin_only(func):
    """Decorator to restrict commands to admin users only"""
    @wraps(func)
    async def wrapped(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("🚫 You are not authorized to use this command.")
            return
        return await func(self, update, context, *args, **kwargs)
    return wrapped

def private_chat_only(func):
    """Decorator to restrict commands to private chats only"""
    @wraps(func)
    async def wrapped(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_chat and update.effective_chat.type == 'private':
            return await func(self, update, context, *args, **kwargs)
        else:
            await update.message.reply_text('❌ Cette commande fonctionne uniquement dans un chat privé.')
    return wrapped
