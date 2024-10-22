import random
import string
import logging
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import verify_linkedin_comment

# Logging and Redis setup remains the same...

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL)

async def load_sent_emails():
    try:
        response = await supabase_manager.client.table(SENT_EMAILS_TABLE).select('*').execute()
        return {str(item['id']): item for item in response.data}
    except Exception as e:
        print(f"Error loading sent emails from Supabase: {str(e)}")
        return {}

async def save_sent_emails(sent_emails):
    try:
        for email_id, email_data in sent_emails.items():
            data_to_insert = {
                "id": str(email_id),
                "email": email_data['email'],
                "status": email_data.get('status', 'sent'),
                "cv_type": email_data['cv_type']
            }
            await supabase_manager.client.table(SENT_EMAILS_TABLE).upsert(data_to_insert).execute()
    except Exception as e:
        print(f"Error saving sent emails to Supabase: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Start command received from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            '👋 Bonjour ! Voici les commandes disponibles :\n\n'
            '/question - Poser une question\n'
            '/liste_questions - Voir et répondre aux questions (réservé aux administrateurs)\n'
            '/sendcv - Recevoir un CV (nécessite de suivre notre page LinkedIn)\n'
            '📄 N\'oubliez pas de suivre notre page LinkedIn avant de demander un CV !'
        )
        print("Start message sent successfully")
    except Exception as e:
        print(f"Error sending start message: {str(e)}")

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir votre question.')
        return

    question_text = ' '.join(context.args)
    user_id = update.effective_user.id

    try:
        await supabase_manager.client.table(QUESTIONS_TABLE).insert({
            "user_id": user_id,
            "question": question_text,
            "answered": False,
            "answer": None
        }).execute()
        print(f"Question saved successfully for user {user_id}")
        await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')
    except Exception as e:
        print(f"Error saving question to Supabase: {str(e)}")
        await update.message.reply_text('❌ Une erreur s\'est produite. Veuillez réessayer plus tard.')



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
                # For admin users, send_email_with_cv should be awaited
                result = await send_email_with_cv(email, cv_type, user_id)
                await update.message.reply_text(result)
                return
            except Exception as e:
                await update.message.reply_text(f"❌ Erreur: {str(e)}")
                return

        # Generate and store verification code for non-admin users
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Store data in Redis
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
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        await query.answer()
        
        if not query.data.startswith("verify_"):
            logger.warning(f"Invalid callback data received: {query.data}")
            return
        
        # Retrieve stored data from Redis
        stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
        stored_email = redis_client.get(f"linkedin_email:{user_id}")
        stored_cv_type = redis_client.get(f"linkedin_cv_type:{user_id}")
        
        # Decode bytes to strings and handle missing data
        stored_data = {
            'code': stored_code.decode('utf-8') if stored_code else None,
            'email': stored_email.decode('utf-8') if stored_email else None,
            'cv_type': stored_cv_type.decode('utf-8') if stored_cv_type else None
        }
        
        logger.info(f"Retrieved stored data for user {user_id}: {stored_data}")
        
        if not all(stored_data.values()):
            await query.message.edit_text("❌ Session expirée. Veuillez recommencer avec /sendcv")
            return
        
        verification_code = query.data.split("_")[1]
        if verification_code != stored_data['code']:
            await query.message.edit_text("❌ Code de vérification invalide. Veuillez réessayer avec /sendcv")
            return
        
        await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")
        
        # Verify LinkedIn comment
        comment_verified = await verify_linkedin_comment(user_id)
        if not comment_verified:
            await query.message.edit_text(
                "❌ Commentaire non trouvé. Assurez-vous d'avoir commenté avec le bon code sur la publication LinkedIn."
            )
            return
        
        await query.message.edit_text("✅ Commentaire vérifié. Envoi du CV en cours...")
        
        try:
            # Send CV and await the result
            result = await send_email_with_cv(stored_data['email'], stored_data['cv_type'], user_id)
            
            # Clean up Redis data
            redis_keys = [
                f"linkedin_verification_code:{user_id}",
                f"linkedin_email:{user_id}",
                f"linkedin_cv_type:{user_id}"
            ]
            redis_client.delete(*redis_keys)
            
            await query.message.edit_text(f"✅ Vérification réussie!\n{result}")
            
        except Exception as e:
            logger.error(f"Error sending CV for user {user_id}: {str(e)}")
            await query.message.edit_text(
                "❌ Une erreur s'est produite lors de l'envoi du CV. Veuillez réessayer avec /sendcv"
            )
            
    except Exception as e:
        logger.error(f"Error in callback handler for user {user_id}: {str(e)}")
        await query.message.edit_text(
            "❌ Une erreur s'est produite. Veuillez réessayer avec /sendcv"
        )


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

def setup_handlers(application):
    """Set up all command handlers"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CommandHandler("question", ask_question))
    application.add_handler(CallbackQueryHandler(callback_handler))
