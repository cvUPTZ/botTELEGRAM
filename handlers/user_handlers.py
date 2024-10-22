import random
import string
import re
import logging
from supabase_config import supabase
import os
import tempfile
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import is_linkedin_verified, get_linkedin_profile
from telegram.ext import CommandHandler
from config import (
    ADMIN_USER_IDS,
    LINKEDIN_REDIRECT_URI,
    QUESTIONS_TABLE,
    SENT_EMAILS_TABLE,
    SCRAPED_DATA_TABLE,
    USERS_TABLE,
    QUESTIONS_FILE,
    SENT_EMAILS_FILE,
    SCRAPED_DATA_FILE,
    REDIS_URL
)

logger = logging.getLogger(__name__)
redis_client = redis.from_url(REDIS_URL)

def load_sent_emails():
    try:
        response = supabase.table(SENT_EMAILS_TABLE).select('*').execute()
        return {str(item['id']): item for item in response.data}
    except Exception as e:
        logger.error(f"Error loading sent emails from Supabase: {str(e)}")
        return {}

def save_sent_emails(sent_emails):
    try:
        for email_id, email_data in sent_emails.items():
            data_to_insert = {
                "id": str(email_id),
                "email": email_data['email'],
                "status": email_data.get('status', 'sent'),
                "cv_type": email_data['cv_type']
            }
            supabase.table(SENT_EMAILS_TABLE).upsert(data_to_insert, on_conflict='id').execute()
    except Exception as e:
        logger.error(f"Error saving sent emails to Supabase: {str(e)}")

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

    try:
        result = supabase.table(QUESTIONS_TABLE).insert({
            "user_id": user_id,
            "question": question_text,
            "answered": False,
            "answer": None
        }).execute()
        logger.info(f"Question saved successfully for user {user_id}")
        await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')
    except Exception as e:
        logger.error(f"Error saving question to Supabase: {str(e)}")
        await update.message.reply_text('❌ Une erreur s\'est produite. Veuillez réessayer plus tard.')

sent_emails = load_sent_emails()

async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"send_cv command received from user {user_id}")
    
    if len(context.args) != 2:
        logger.info(f"Incorrect number of arguments provided by user {user_id}. Sending usage instructions.")
        await send_usage_instructions(update.message)
        return
    
    email, cv_type = context.args
    logger.info(f"User {user_id} requested CV type '{cv_type}' to be sent to {email}")
    
    if cv_type.lower() not in ['junior', 'senior']:
        logger.info(f"Invalid CV type '{cv_type}' requested by user {user_id}")
        await update.message.reply_text('❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".')
        return
    
    is_admin = user_id in ADMIN_USER_IDS
    
    if not is_admin:
        if not is_linkedin_verified(user_id):
            logger.info(f"User {user_id} is not LinkedIn verified. Starting verification process.")
            await start_linkedin_verification(update, context, user_id, cv_type, email)
            return
        
    try:
        result = await send_email_with_cv(email, cv_type, user_id)
        logger.info(f"CV sending result for user {user_id}: {result}")
        await update.message.reply_text(result)
        
        sent_emails[str(user_id)] = {
            'email': email,
            'cv_type': cv_type,
            'status': 'sent'
        }
        save_sent_emails(sent_emails)
    except Exception as e:
        logger.error(f"Error in send_cv for user {user_id}: {str(e)}", exc_info=True)
        await update.message.reply_text('❌ Une erreur s\'est produite lors de l\'envoi du CV. Veuillez réessayer plus tard.')

async def send_usage_instructions(message):
    await message.reply_text(
        '❌ Format de commande incorrect. Utilisez :\n'
        '/sendcv [email] [junior|senior]\n\n'
        'Exemple : /sendcv email@gmail.com junior'
    )

async def start_linkedin_verification(update, context, user_id, cv_type, email):
    verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    redis_client.set(f"linkedin_verification_code:{user_id}", verification_code, ex=3600)

    linkedin_post_url = "https://www.linkedin.com/feed/update/urn:li:activity:7254038723820949505"
    message = (
        f"Pour vérifier votre compte LinkedIn, veuillez commenter le code suivant sur cette publication : {linkedin_post_url}\n"
        f"Code de vérification: {verification_code}"
    )
    
    await update.message.reply_text(message)

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

def setup_handlers(application):
    """Set up all command handlers"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("question", ask_question))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
