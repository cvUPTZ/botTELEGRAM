import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv

logger = logging.getLogger(__name__)

# Define conversation states
LINKEDIN_CONFIRMATION, EMAIL_CV_TYPE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Start command received from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            '👋 Bonjour ! Voici les commandes disponibles :\n\n'
            '/question - Poser une question\n'
            '/liste_questions - Voir et répondre aux questions (réservé aux administrateurs)\n'
            '/sendcv - Recevoir un CV (nécessite de suivre notre page LinkedIn)\n'
            '📄 N\'oubliez pas de suivre notre page LinkedIn avant de demander un CV !'
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
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    topic_id = 3137
    if update.effective_message.message_thread_id != topic_id:
        await update.effective_message.reply_text('🚫 Cette commande est restreinte au topic CV_UP إحصل على نموذج السيرة')
        return ConversationHandler.END

    # Create inline keyboard for LinkedIn confirmation
    keyboard = [
        [InlineKeyboardButton("✅ J'ai suivi la page", callback_data='linkedin_followed')],
        [InlineKeyboardButton("❌ Annuler", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_text(
        "Avant de recevoir votre CV, veuillez suivre notre page LinkedIn:\n"
        "https://www.linkedin.com/company/cv-updz\n\n"
        "Une fois que vous avez suivi la page, cliquez sur le bouton ci-dessous.",
        reply_markup=reply_markup
    )

    return LINKEDIN_CONFIRMATION

async def linkedin_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == 'cancel':
        await query.edit_message_text("Opération annulée. Utilisez /sendcv pour recommencer.")
        return ConversationHandler.END

    await query.edit_message_text("Merci d'avoir suivi notre page LinkedIn!")
    await query.message.reply_text(
        "Maintenant, veuillez fournir votre email et le type de CV souhaité (junior ou senior) dans le format suivant:\n"
        "email@example.com junior"
    )

    return EMAIL_CV_TYPE

async def process_email_cv_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    input_text = update.message.text
    parts = re.split(r'[ ,;:|\t]+', input_text)

    if len(parts) != 2:
        await update.message.reply_text('❌ Format invalide. Veuillez utiliser: email@example.com junior|senior')
        return EMAIL_CV_TYPE

    email, cv_type = parts
    user_id = update.effective_user.id

    if cv_type.lower() not in ['junior', 'senior']:
        await update.message.reply_text('❌ Type de CV invalide. Choisissez "junior" ou "senior".')
        return EMAIL_CV_TYPE

    result = await send_email_with_cv(email, cv_type.lower(), user_id)
    await update.message.reply_text(result)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Opération annulée. Utilisez /sendcv pour recommencer.')
    return ConversationHandler.END

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

# Create the conversation handler
cv_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("sendcv", send_cv)],
    states={
        LINKEDIN_CONFIRMATION: [CallbackQueryHandler(linkedin_confirmation)],
        EMAIL_CV_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_email_cv_type)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)