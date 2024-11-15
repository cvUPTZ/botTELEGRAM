# handlers/user_handlers.py
import logging
import re
from telegram import Update
from telegram.ext import ContextTypes
from utils.email_utils import send_email_with_cv
from utils.db_utils import save_question
from config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    logger.info(f"Start command received from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            '👋 Bonjour ! Voici les commandes disponibles :\n\n'
            '/question - Poser une question\n'
            '/liste_questions - Voir et répondre aux questions (réservé aux administrateurs)\n'
            '/sendcv - Recevoir un CV\n'
            '/myid - Voir votre ID'
        )
    except Exception as e:
        logger.error(f"Error sending start message: {str(e)}")

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /question command"""
    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir votre question.')
        return

    question_text = ' '.join(context.args)
    user_id = update.effective_user.id

    try:
        await save_question(user_id, question_text)
        await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')
    except Exception as e:
        logger.error(f"Error saving question: {str(e)}")
        await update.message.reply_text('❌ Une erreur est survenue lors de l\'enregistrement de votre question.')

async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /sendcv command"""
    try:
        if not context.args or len(context.args) != 2:
            await update.message.reply_text(
                '❌ Format: /sendcv [email] [junior|senior]\n'
                'Exemple: /sendcv email@example.com junior'
            )
            return

        email = context.args[0].lower()
        cv_type = context.args[1].lower()

        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            await update.message.reply_text('❌ Format d\'email invalide.')
            return

        # Validate CV type
        if cv_type not in ['junior', 'senior']:
            await update.message.reply_text('❌ Type de CV invalide. Utilisez "junior" ou "senior".')
            return

        result = await send_email_with_cv(email, cv_type, update.effective_user.id, context)
        await update.message.reply_text(result)

    except Exception as e:
        logger.error(f"Error in send_cv: {str(e)}", exc_info=True)
        await update.message.reply_text('❌ Une erreur est survenue lors de l\'envoi du CV.')

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /myid command"""
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')
