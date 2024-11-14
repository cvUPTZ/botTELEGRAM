import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import json
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv
from config import (
    SENT_EMAILS_FILE,
    QUESTIONS_FILE
)

logger = logging.getLogger(__name__)

# Example admin user IDs (replace with your actual admin IDs)
ADMIN_IDS = {1719899525, 987654321}  # Add your actual admin user IDs here

def save_sent_emails(sent_emails):
    try:
        with open(SENT_EMAILS_FILE, 'w') as json_file:
            json.dump(sent_emails, json_file, indent=4)
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
            '/sendcv - Recevoir un CV\n'
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

# Load sent emails at the beginning of your script
sent_emails = load_sent_emails()

@private_chat_only
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    # Check if any arguments were provided
    if not context.args or len(context.args) != 2:
        await send_usage_instructions(update.message)
        return

    # Get email and CV type from arguments
    email = context.args[0]
    cv_type = context.args[1].lower()

    # Validate CV type
    if cv_type not in ['junior', 'senior']:
        await update.message.reply_text('❌ Type de CV invalide. Utilisez "junior" ou "senior".')
        return

    # Validate email format
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text('❌ Format d\'email invalide.')
        return

    try:
        # Send the CV
        result = await send_email_with_cv(email, cv_type, user_id, context.bot.supabase)
        
        # Send the result message back to the user
        await update.message.reply_text(result)
        
        # If successful, save to sent emails record
        if result.startswith('✅'):
            sent_emails[str(user_id)] = {
                'email': email,
                'cv_type': cv_type,
                'timestamp': str(datetime.now())
            }
            save_sent_emails(sent_emails)
            
    except Exception as e:
        logger.error(f"Error sending CV: {str(e)}")
        await update.message.reply_text('❌ Une erreur est survenue. Veuillez réessayer plus tard.')

async def send_usage_instructions(message):
    await message.reply_text(
        '❌ Format de commande incorrect. Utilisez :\n'
        '/sendcv [email] [junior|senior]\n\n'
        'Exemple : /sendcv email@gmail.com junior'
    )

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')
