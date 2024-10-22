import random
import string
import re
import logging
from supabase_config import supabase
import os
import tempfile
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler  # Add CallbackQueryHandler
from telegram.ext import ContextTypes
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import is_linkedin_verified, get_linkedin_profile, verify_linkedin_comment
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

# Configure logging at the module level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Redis client
# redis_client = redis.from_url(REDIS_URL)


redis_client = redis.from_url(REDIS_URL)

# from telegram.ext import ContextTypes
# from config import ADMIN_USER_IDS, REDIS_URL
# from utils.email_utils import send_email_with_cv
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
    try:
        user_id = update.effective_user.id
        
        if len(context.args) != 2:
            await update.message.reply_text(
                '❌ Format incorrect. Utilisez:\n'
                '/sendcv [email] [junior|senior]\n'
                'Exemple: /sendcv email@example.com junior'
            )
            return
        
        email, cv_type = context.args
        cv_type = cv_type.lower()
        
        if cv_type not in ['junior', 'senior']:
            await update.message.reply_text('❌ Type de CV incorrect. Utilisez "junior" ou "senior".')
            return
        
        if user_id in ADMIN_USER_IDS:
            try:
                result = await send_email_with_cv(email, cv_type, user_id)
                await update.message.reply_text(result)
                return
            except Exception as e:
                await update.message.reply_text(f"❌ Erreur: {str(e)}")
                return
        
        # Generate verification code for non-admin users
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Store data in Redis with expiration
        redis_client.setex(f"linkedin_verification_code:{user_id}", 3600, verification_code)
        redis_client.setex(f"linkedin_email:{user_id}", 3600, email)
        redis_client.setex(f"linkedin_cv_type:{user_id}", 3600, cv_type)

        linkedin_post_url = "https://www.linkedin.com/feed/update/urn:li:activity:7254038723820949505"
        
        keyboard = [
            [InlineKeyboardButton("📝 Voir la publication LinkedIn", url=linkedin_post_url)],
            [InlineKeyboardButton("✅ J'ai commenté", callback_data=f"verify_{verification_code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Pour recevoir votre CV, veuillez:\n\n"
            f"1. Cliquer sur le bouton ci-dessous pour voir la publication\n"
            f"2. Commenter avec ce code: {verification_code}\n"
            f"3. Revenir ici et cliquer sur 'J'ai commenté'\n\n"
            f"⚠️ Le code est valide pendant 1 heure",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in send_cv command: {str(e)}")
        await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries for LinkedIn verification process.
    """
    try:
        query = update.callback_query
        user_id = update.effective_user.id
        
        # Answer the callback query to remove the loading state
        await query.answer()

        print(f"[DEBUG] Received callback data: {query.data}")

        # Verify the callback data format
        if not query.data.startswith("verify_"):
            print(f"[ERROR] Invalid callback data format: {query.data}")
            await query.message.edit_text("❌ Format de vérification invalide")
            return
                
        # Retrieve stored data from Redis
        stored_data = {
            'code': redis_client.get(f"linkedin_verification_code:{user_id}"),
            'email': redis_client.get(f"linkedin_email:{user_id}"),
            'cv_type': redis_client.get(f"linkedin_cv_type:{user_id}")
        }
        
        print(f"[DEBUG] Retrieved stored data: {stored_data}")
        
        # Decode Redis values
        stored_data = {k: v.decode('utf-8') if v else None for k, v in stored_data.items()}
        print(f"[DEBUG] Decoded stored data: {stored_data}")
        
        # Check if all required data is present
        if not all(stored_data.values()):
            print(f"[ERROR] Missing stored data for user {user_id}")
            await query.message.edit_text("❌ Session expirée. Veuillez recommencer avec /sendcv")
            return
        
        # Extract and verify the verification code
        verification_code = query.data.split("_")[1]
        print(f"[DEBUG] Verifying code: {verification_code} against stored: {stored_data['code']}")
        
        if verification_code != stored_data['code']:
            print(f"[ERROR] Verification code mismatch for user {user_id}")
            await query.message.edit_text("❌ Code de vérification invalide. Veuillez réessayer avec /sendcv")
            return
        
        # Update message to show verification status
        await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")

        # Verify LinkedIn comment
        print(f"[DEBUG] Starting LinkedIn comment verification for user {user_id}")
        comment_verified = await verify_linkedin_comment(user_id)
        
        print(f"[DEBUG] Comment verification result for user {user_id}: {comment_verified}")
        
        if not comment_verified:
            await query.message.edit_text(
                "❌ Commentaire non trouvé. Assurez-vous d'avoir:\n\n"
                "1. Commenté la publication LinkedIn\n"
                "2. Utilisé le code exact\n"
                "3. Attendu quelques secondes après avoir commenté\n\n"
                "Vous pouvez réessayer en cliquant sur 'J'ai commenté'"
            )
            return
        
        # Show CV sending status
        await query.message.edit_text("✅ Commentaire vérifié. Envoi du CV en cours...")

        # Send CV
        print(f"[DEBUG] Sending CV to {stored_data['email']} (type: {stored_data['cv_type']})")
        result = await send_email_with_cv(stored_data['email'], stored_data['cv_type'], user_id)
        
        # Clean up Redis data
        redis_keys = [
            f"linkedin_verification_code:{user_id}",
            f"linkedin_email:{user_id}",
            f"linkedin_cv_type:{user_id}"
        ]
        redis_client.delete(*redis_keys)
        print(f"[DEBUG] Cleaned up Redis keys for user {user_id}")
        
        await query.message.edit_text(f"✅ Vérification réussie!\n{result}")
        
    except Exception as e:
        print(f"[ERROR] Error in callback handler: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        await query.message.edit_text(
            "❌ Une erreur s'est produite lors de la vérification. Veuillez réessayer avec /sendcv"
        )
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
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CallbackQueryHandler(callback_handler))  # Add this line


    application.add_handler(CommandHandler("verify_linkedin", start_linkedin_verification))
