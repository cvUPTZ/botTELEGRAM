import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import private_chat_only
from utils.file_utils import load_questions, save_questions
from utils.email_utils import send_email_with_cv
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
        # If the file doesn't exist, return an empty dictionary
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



# Load sent emails at the beginning of your script
sent_emails = load_sent_emails()

    
    

# Example admin user IDs (replace with your actual admin IDs)
ADMIN_IDS = {1719899525, 987654321}  # Add your actual admin user IDs here
#  []
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
    
    # Validate the email format
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.effective_message.reply_text('❌ Format d\'email invalide. Veuillez essayer à nouveau.')
        return
    
    # Check if the cv_type is valid
    if cv_type.lower() not in ['junior', 'senior']:
        await update.effective_message.reply_text('❌ Type de CV invalide. Choisissez "junior" ou "senior".')
        return
    
    user_id = update.effective_user.id  # Get the user ID
    is_admin = user_id in ADMIN_IDS  # Check if the user is an admin

    # If user is not admin, check if they have already requested a CV
    if not is_admin and user_id in sent_emails:
        await update.effective_message.reply_text('❌ Vous avez déjà reçu un CV. Vous ne pouvez pas en demander un autre.')
        return
    
    # For admins: Allow multiple CV types for the same user ID
    if is_admin:
        # If the admin sends a CV request, we can update or add the CV type and email
        sent_emails[user_id] = {
            "cv_type": cv_type.lower(),
            "email": email
        }
    else:
        # New user: Allow the request and save the CV type
        sent_emails[user_id] = {
            "cv_type": cv_type.lower(),
            "email": email
        }

    # Send email with the CV
    result = await send_email_with_cv(email, cv_type.lower(), user_id)

    # Save the updated sent emails to JSON
    save_sent_emails(sent_emails)

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
