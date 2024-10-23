from datetime import datetime
import time
import random
import string
import logging
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from utils.decorators import private_chat_only
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import TokenManager
from config import (
    ADMIN_USER_IDS,
    # QUESTIONS_TABLE,
    SENT_EMAILS_TABLE,
    USERS_TABLE,
    REDIS_URL
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Redis client and TokenManager
redis_client = redis.from_url(REDIS_URL)
token_manager = TokenManager()

@private_chat_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    logger.info(f"Start command received from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            '👋 Bonjour ! Voici les commandes disponibles :\n\n'
            '/question - Poser une question\n'
            '/liste_questions - Voir et répondre aux questions (réservé aux administrateurs)\n'
            '/sendcv - Recevoir un CV (nécessite de suivre notre page LinkedIn)\n'
            '/admin_auth - Authentifier LinkedIn (réservé aux administrateurs)\n'
            '📄 N\'oubliez pas de suivre notre page LinkedIn avant de demander un CV !'
        )
        logger.info("Start message sent successfully")
    except Exception as e:
        logger.error(f"Error sending start message: {str(e)}")
        await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")

@private_chat_only
async def admin_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle LinkedIn authentication for admins"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text('❌ Cette commande est réservée aux administrateurs.')
        return
        
    try:
        # Generate auth URL
        auth_url = token_manager.get_auth_url()
        
        keyboard = [[InlineKeyboardButton("🔐 Authentifier LinkedIn", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔄 Veuillez suivre ces étapes:\n\n"
            "1. Cliquez sur le bouton ci-dessous\n"
            "2. Connectez-vous à LinkedIn\n"
            "3. Autorisez l'application\n"
            "4. Copiez le code de la redirection\n"
            "5. Utilisez /auth_callback [code] pour terminer",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in admin_auth: {str(e)}")
        await update.message.reply_text("❌ Une erreur s'est produite lors de l'authentification.")

@private_chat_only
async def auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle LinkedIn authentication callback for admins"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text('❌ Cette commande est réservée aux administrateurs.')
        return
        
    if not context.args:
        await update.message.reply_text('❌ Veuillez fournir le code d\'autorisation.')
        return
        
    try:
        code = context.args[0]
        result = await token_manager.initialize_token(code)
        
        if result:
            await update.message.reply_text('✅ Authentification LinkedIn réussie!')
            # Notify all admins
            for admin_id in ADMIN_USER_IDS:
                if admin_id != user_id:
                    try:
                        await context.bot.send_message(
                            admin_id,
                            f"ℹ️ LinkedIn a été ré-authentifié par l'administrateur {user_id}"
                        )
                    except Exception:
                        logger.error(f"Failed to notify admin {admin_id}")
        else:
            await update.message.reply_text('❌ Échec de l\'authentification. Veuillez réessayer.')
            
    except Exception as e:
        logger.error(f"Error in auth_callback: {str(e)}")
        await update.message.reply_text("❌ Une erreur s'est produite lors de l'authentification.")

@private_chat_only
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /sendcv command"""
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
        
        # Admin bypass for LinkedIn verification
        if user_id in ADMIN_USER_IDS:
            try:
                result = await send_email_with_cv(
                    email, 
                    cv_type, 
                    user_id, 
                    context.application.supabase
                )
                await update.message.reply_text(result)
                return
            except Exception as e:
                logger.error(f"Error sending CV for admin {user_id}: {str(e)}")
                await update.message.reply_text(f"❌ Erreur: {str(e)}")
                return

        # Check if authentication is needed
        if redis_client.get('linkedin_auth_needed'):
            # Notify admins that authentication is needed
            notification = (
                "🔴 Attention: L'authentification LinkedIn est nécessaire.\n"
                f"Demande de CV en attente de l'utilisateur {user_id}.\n"
                "Utilisez /admin_auth pour ré-authentifier."
            )
            for admin_id in ADMIN_USER_IDS:
                try:
                    await context.bot.send_message(admin_id, notification)
                except Exception:
                    logger.error(f"Failed to notify admin {admin_id}")
                    
            await update.message.reply_text(
                "⏳ Nous rencontrons un problème technique temporaire.\n"
                "Les administrateurs ont été notifiés et traiteront votre demande dès que possible.\n"
                "Veuillez réessayer dans quelques minutes."
            )
            return

        # Check previous CV sends
        try:
            response = context.application.supabase.table(SENT_EMAILS_TABLE)\
                .select('*')\
                .filter('email', 'eq', email)\
                .execute()

            if response.data:
                previous_send = response.data[0]
                if previous_send['cv_type'] == cv_type:
                    await update.message.reply_text(f'📩 Vous avez déjà reçu un CV de type {cv_type}.')
                    return
                else:
                    await update.message.reply_text(f'📩 Vous avez déjà reçu un CV de type {previous_send["cv_type"]}.')
                    return

        except Exception as e:
            logger.error(f"Error checking previous CV sends: {str(e)}")
        
        # Generate verification code
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        current_timestamp = str(int(datetime.utcnow().timestamp()))
        
        # Store verification data in Redis
        redis_client.setex(f"linkedin_verification_code:{user_id}", 3600, verification_code)
        redis_client.setex(f"linkedin_code_timestamp:{user_id}", 3600, current_timestamp)
        redis_client.setex(f"linkedin_email:{user_id}", 3600, email)
        redis_client.setex(f"linkedin_cv_type:{user_id}", 3600, cv_type)
        
        linkedin_post_url = "https://www.linkedin.com/feed/update/urn:li:activity:7254038723820949505"
        
        keyboard = [
            [InlineKeyboardButton("📝 Voir la publication LinkedIn", url=linkedin_post_url)],
            [InlineKeyboardButton("✅ J'ai commenté", callback_data=f"verify_{verification_code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        instructions = (
            f"Pour recevoir votre CV, veuillez suivre ces étapes dans l'ordre :\n\n"
            f"1. Cliquer sur le bouton ci-dessous pour voir la publication\n"
            f"2. Suivre notre page LinkedIn\n"
            f"3. Commenter avec exactement ce code : {verification_code}\n"
            f"4. Revenir ici et cliquer sur 'J'ai commenté'\n\n"
            f"⚠️ Important:\n"
            f"- Le code est valide pendant 1 heure\n"
            f"- Vous devez suivre les étapes dans l'ordre\n"
            f"- Les commentaires faits avant la génération du code ne sont pas valides\n"
            f"- Un seul CV par adresse email"
        )
        
        await update.message.reply_text(instructions, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in send_cv command: {str(e)}")
        await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")

async def verify_linkedin_comment(user_id: str) -> Tuple[bool, str]:
    """
    Verify if a user has commented on the LinkedIn post with their verification code
    Returns tuple of (success, message)
    """
    stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
    
    if not stored_code:
        return False, "Code de vérification non trouvé. Veuillez recommencer."
        
    stored_code = stored_code.decode('utf-8') if isinstance(stored_code, bytes) else stored_code
    
    try:
        # Get valid token
        access_token = await token_manager.get_valid_token()
        if not access_token:
            return False, "Erreur d'authentification LinkedIn. Veuillez réessayer plus tard."
        
        post_id = "7254038723820949505"
        comments_url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202304"
        }
        
        response = await asyncio.to_thread(
            requests.get,
            comments_url,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 401:
            logger.error("LinkedIn token expired")
            return False, "Erreur d'authentification LinkedIn. Veuillez réessayer plus tard."
            
        response.raise_for_status()
        comments = response.json().get('elements', [])
        
        if not comments:
            return False, "Aucun commentaire trouvé. Assurez-vous d'avoir commenté avec le code fourni."

        # Get timestamp when code was generated
        code_timestamp = redis_client.get(f"linkedin_code_timestamp:{user_id}")
        if not code_timestamp:
            return False, "Session expirée. Veuillez recommencer."
            
        code_timestamp = float(code_timestamp.decode('utf-8'))
        
        # Look for the exact code in comments
        code_found = False
        for comment in comments:
            comment_text = comment.get('message', {}).get('text', '').strip()
            comment_time = int(comment.get('created', {}).get('time', 0)) / 1000  # Convert to seconds
            
            if stored_code == comment_text:  # Exact match only
                if comment_time < code_timestamp:
                    continue  # Skip comments made before code generation
                code_found = True
                break
        
        if not code_found:
            return False, "Code de vérification non trouvé dans les commentaires. Assurez-vous d'avoir copié exactement le code fourni."
        
        return True, "Vérification réussie!"
        
    except Exception as e:
        logger.error(f"Error verifying LinkedIn comment: {str(e)}", exc_info=True)
        return False, "Une erreur est survenue lors de la vérification. Veuillez réessayer plus tard."


async def handle_linkedin_verification(query, user_id, context):
    """Handle LinkedIn verification process"""
    try:
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
        
        if not all(stored_data.values()):
            await query.message.edit_text("❌ Session expirée. Veuillez recommencer avec /sendcv")
            return
        
        verification_code = query.data.split("_")[1]
        if verification_code != stored_data['code']:
            await query.message.edit_text("❌ Code de vérification invalide. Veuillez recommencer avec /sendcv")
            return
        
        await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")
        
        verified, message = await verify_linkedin_comment(user_id)
        if not verified:
            await query.message.edit_text(message)
            return
        
        # Send CV without await for Supabase
        result = await send_email_with_cv(
            stored_data['email'],
            stored_data['cv_type'],
            user_id,
            context.bot.supabase
        )
        
        # Clean up Redis data
        redis_keys = [
            f"linkedin_verification_code:{user_id}",
            f"linkedin_code_timestamp:{user_id}",
            f"linkedin_email:{user_id}",
            f"linkedin_cv_type:{user_id}"
        ]
        redis_client.delete(*redis_keys)
        
        await query.message.edit_text(result)
        
    except Exception as e:
        logger.error(f"Error in LinkedIn verification: {str(e)}")
        await query.message.edit_text("❌ Une erreur s'est produite. Veuillez réessayer avec /sendcv")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        await query.answer()
        
        if query.data.startswith("verify_"):
            await handle_linkedin_verification(query, user_id, context)
        elif query.data.startswith("answer_"):
            await handle_answer_question(query, context)
        elif query.data.startswith("delete_"):
            await handle_delete_question(query, context)
            
    except Exception as e:
        logger.error(f"Error in callback handler: {str(e)}")
        await query.message.edit_text("❌ Une erreur s'est produite. Veuillez réessayer.")

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

def setup_handlers(application):
    """Set up all command handlers"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    # application.add_handler(CommandHandler("question", ask_question))
    # application.add_handler(CommandHandler("liste_questions", list_questions))
    application.add_handler(CommandHandler("admin_auth", admin_auth))
    application.add_handler(CommandHandler("auth_callback", auth_callback))
    application.add_handler(CallbackQueryHandler(callback_handler))
