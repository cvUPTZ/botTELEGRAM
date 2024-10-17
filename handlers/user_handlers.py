import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Start command received from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            '👋 Bonjour ! Utilisez /question pour poser une question, /liste_questions pour voir et répondre aux questions (réservé aux administrateurs), ou /sendcv pour recevoir un CV. 📄'
        )
        logger.info("Start message sent successfully")
    except Exception as e:
        logger.error(f"Error sending start message: {str(e)}")

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir votre question.')
        return

    question_text = ' '.join(context.args)
    user_id = update.effective_user.id

    questions, next_id = load_questions()
    questions[str(next_id)] = {
        'user_id': user_id,
        'question': question_text,
        'answered': False
    }
    save_questions(questions)

    await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')

@private_chat_only
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic_id = 3137
    if update.effective_message.message_thread_id != topic_id:
        await update.effective_message.reply_text('🚫 Cette commande est restreinte au topic CV_UP إحصل على نموذج السيرة')
        return
    
    if not context.args:
        await send_usage_instructions(update.effective_message)
        return
    
    input_text = ' '.join(context.args)
    parts = re.split(r'[ ,;:|\t]+', input_text)
    
    if len(parts) != 2:
        await send_usage_instructions(update.effective_message)
        return
    
    email, cv_type = parts
    
    if cv_type.lower() not in ['junior', 'senior']:
        await update.effective_message.reply_text('❌ Type de CV invalide. Choisissez "junior" ou "senior".')
        return
    
    result = await send_email_with_cv(email, cv_type.lower())
    await update.effective_message.reply_text(result)

async def send_usage_instructions(message):
    await message.reply_text(
        '❌ Format de commande incorrect. Utilisez :\n'
        '/sendcv [email] [junior|senior]\n\n'
        'Exemple : /sendcv email@gmail.com junior'
    )

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')
