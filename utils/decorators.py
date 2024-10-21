from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_USER_IDS

def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("🚫 You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def private_chat_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_chat.type !== 'private':
            await update.message.reply_text("🚫 This command can only be used in private chats.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped
