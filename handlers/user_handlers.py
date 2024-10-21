import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import is_linkedin_verified, get_linkedin_profile
from config import LINKEDIN_REDIRECT_URI

import json  # Import json for saving data to JSON files
from config import (
    QUESTIONS_TABLE,
    SENT_EMAILS_TABLE,
    SCRAPED_DATA_TABLE,
    USERS_TABLE,
    QUESTIONS_FILE,  # Add this constant for JSON file paths
    SENT_EMAILS_FILE,
    SCRAPED_DATA_FILE,
)

logger = logging.getLogger(__name__)

def save_sent_emails(sent_emails):
    try:
        with open(SENT_EMAILS_FILE, 'w') as json_file:
            json.dump(sent_emails, json_file, indent=4)  # Using indent for pretty printing
    except Exception as e:
        logger.error(f"Error saving sent emails to JSON file: {str(e)}")
        
def load_sent_emails():
    try:
        with open(SENT_EMAILS_FILE, 'r') as json_file:
            return json.load(json_file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.error("Error decoding JSON from the sent emails file")
        return {}
    except Exception as e:
        logger.error(f"Error loading sent emails from JSON file: {str(e)}")
        return {}

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


sent_emails = load_sent_emails()

ADMIN_IDS = {1719899525, 987654321}  # Replace with actual admin IDs
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"send_cv command received from user {user_id}")
    
    # Check if the right number of arguments is provided
    if len(context.args) != 2:
        logger.info(f"Incorrect number of arguments provided by user {user_id}. Sending usage instructions.")
        await send_usage_instructions(update.message)
        return
    
    # Extract the email and CV type from user input
    email, cv_type = context.args
    logger.info(f"User {user_id} requested CV type '{cv_type}' to be sent to {email}")
    
    # Check if the CV type is valid (either 'junior' or 'senior')
    if cv_type.lower() not in ['junior', 'senior']:
        logger.info(f"Invalid CV type '{cv_type}' requested by user {user_id}")
        await update.message.reply_text('❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".')
        return
    
    # Check if the user is LinkedIn verified
    if not is_linkedin_verified(user_id):
        logger.info(f"User {user_id} is not LinkedIn verified. Starting verification process.")
        await verify_linkedin(update, context, user_id, cv_type)
        return
    
    try:
        # User is verified, send the CV
        logger.info(f"Attempting to send CV to {email} for user {user_id}")
        result = await send_email_with_cv(email, cv_type, user_id)
        logger.info(f"CV sending result for user {user_id}: {result}")
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Error in send_cv for user {user_id}: {str(e)}", exc_info=True)
        await update.message.reply_text('❌ Une erreur s\'est produite lors de l\'envoi du CV. Veuillez réessayer plus tard.')

async def start_linkedin_verification(update, context, user_id, cv_type):
    # This function will handle the LinkedIn verification process
    # It should redirect the user to the LinkedIn authorization URL
    # and then handle the callback to complete the verification
    auth_url = f"{LINKEDIN_REDIRECT_URI.replace('/linkedin-callback', '')}/start-linkedin-auth/{user_id}/{cv_type}"
    keyboard = [[InlineKeyboardButton("Vérifiez avec LinkedIn", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Veuillez cliquer sur le bouton ci-dessous pour vérifier votre profil LinkedIn:",
        reply_markup=reply_markup
    )
async def send_usage_instructions(message):
    await message.reply_text(
        '❌ Format de commande incorrect. Utilisez :\n'
        '/sendcv [email] [junior|senior]\n\n'
        'Exemple : /sendcv email@gmail.com junior'
    )


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')
