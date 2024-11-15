# handlers/user_handlers.py
import logging
import re
from telegram import Update
from telegram.ext import ContextTypes
from telegram.request import HTTPXRequest
from utils.email_utils import send_email_with_cv
from config import ADMIN_USER_IDS
import asyncio
# Configure logging
logger = logging.getLogger(__name__)

# Configure custom request parameters for better Lambda performance
REQUEST_KWARGS = {
    "connection_pool_size": 8,
    "connect_timeout": 20.0,
    "read_timeout": 20.0,
    "write_timeout": 20.0,
    "pool_timeout": 3.0,
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    logger.info(f"Start command received from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            '👋 Bonjour ! Voici les commandes disponibles :\n\n'
            '/sendcv - Recevoir un CV\n'
            '/myid - Voir votre ID',
            request_kwargs=REQUEST_KWARGS
        )
    except Exception as e:
        logger.error(f"Error sending start message: {str(e)}", exc_info=True)
        await handle_error_with_retry(update, "Error sending start message")

async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /sendcv command"""
    try:
        if not context.args or len(context.args) != 2:
            await update.message.reply_text(
                '❌ Format: /sendcv [email] [junior|senior]\n'
                'Exemple: /sendcv email@example.com junior',
                request_kwargs=REQUEST_KWARGS
            )
            return

        email = context.args[0].lower()
        cv_type = context.args[1].lower()

        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            await update.message.reply_text(
                '❌ Format d\'email invalide.',
                request_kwargs=REQUEST_KWARGS
            )
            return

        # Validate CV type
        if cv_type not in ['junior', 'senior']:
            await update.message.reply_text(
                '❌ Type de CV invalide. Utilisez "junior" ou "senior".',
                request_kwargs=REQUEST_KWARGS
            )
            return

        result = await send_email_with_cv(email, cv_type, update.effective_user.id, context)
        await update.message.reply_text(
            result,
            request_kwargs=REQUEST_KWARGS
        )

    except Exception as e:
        logger.error(f"Error in send_cv: {str(e)}", exc_info=True)
        await handle_error_with_retry(update, "Une erreur est survenue lors de l'envoi du CV")

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /myid command"""
    try:
        user_id = update.effective_user.id
        await update.message.reply_text(
            f'🔍 Votre ID est : {user_id}',
            request_kwargs=REQUEST_KWARGS
        )
    except Exception as e:
        logger.error(f"Error in my_id: {str(e)}", exc_info=True)
        await handle_error_with_retry(update, "Error retrieving ID")

async def handle_error_with_retry(update: Update, message: str, max_retries: int = 3) -> None:
    """Handle errors with retry logic"""
    for attempt in range(max_retries):
        try:
            await update.message.reply_text(
                f'❌ {message}',
                request_kwargs=REQUEST_KWARGS
            )
            break
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to send error message after {max_retries} attempts: {str(e)}", exc_info=True)
            else:
                await asyncio.sleep(1)  # Wait before retry
