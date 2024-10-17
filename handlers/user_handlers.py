import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv

logger = logging.getLogger(__name__)

@private_chat_only
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            '❌ Format de commande incorrect. Utilisez :\n'
            '/sendcv [email] [junior|senior]\n\n'
            'Exemple : /sendcv email@gmail.com junior'
        )
        return

    # Join the arguments into a single string and split using various separators
    input_text = ' '.join(context.args)
    # Split using multiple separators: spaces, commas, semicolons, colons, pipes, and tabs
    parts = re.split(r'[ ,;:|\t]+', input_text)

    if len(parts) != 2:
        await update.message.reply_text(
            '❌ Format de commande incorrect. Utilisez :\n'
            '/sendcv [email] [junior|senior]\n\n'
            'Exemple : /sendcv email@gmail.com junior'
        )
        return

    email, cv_type = parts

    result = await send_email_with_cv(email, cv_type)
    await update.message.reply_text(result)
