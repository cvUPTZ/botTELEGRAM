import logging
import random
import string
from datetime import datetime
from typing import Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from utils.decorators import private_chat_only
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import (
    LinkedInAuthManager,
    TokenManager,
    LinkedInVerificationManager,
    REDIS_KEYS
)
from config import (
    ADMIN_USER_IDS,
    SENT_EMAILS_TABLE,
    VERIFICATION_CODE_LENGTH,
    LINKEDIN_POST_URL
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UserCommandHandler:
    """Handle user commands and interactions"""
    def __init__(self, redis_client, supabase_client):
        self.redis_client = redis_client
        self.supabase = supabase_client
        self.token_manager = TokenManager(redis_client)
        self.auth_manager = LinkedInAuthManager(redis_client)
        self.verification_manager = LinkedInVerificationManager(redis_client, self.token_manager)

    @private_chat_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    async def admin_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle LinkedIn authentication for admins"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text('❌ Cette commande est réservée aux administrateurs.')
            return
            
        try:
            auth_url = self.auth_manager.get_auth_url()
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
    async def auth_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            result = await self.auth_manager.initialize_token(code)
            
            if result:
                await update.message.reply_text('✅ Authentification LinkedIn réussie!')
                await self.notify_other_admins(context, user_id)
            else:
                await update.message.reply_text('❌ Échec de l\'authentification. Veuillez réessayer.')
                
        except Exception as e:
            logger.error(f"Error in auth_callback: {str(e)}")
            await update.message.reply_text("❌ Une erreur s'est produite lors de l'authentification.")

    async def notify_other_admins(self, context: ContextTypes.DEFAULT_TYPE, initiator_id: int) -> None:
        """Notify other admins about authentication"""
        for admin_id in ADMIN_USER_IDS:
            if admin_id != initiator_id:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"ℹ️ LinkedIn a été ré-authentifié par l'administrateur {initiator_id}"
                    )
                except Exception:
                    logger.error(f"Failed to notify admin {admin_id}")

    @private_chat_only
    async def send_cv(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            
            result = await self.handle_cv_request(update, context, user_id, email, cv_type)
            await update.message.reply_text(result[1], reply_markup=result[0] if result[0] else None)
            
        except Exception as e:
            logger.error(f"Error in send_cv command: {str(e)}")
            await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")

    async def handle_cv_request(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        email: str,
        cv_type: str
    ) -> Tuple[Optional[InlineKeyboardMarkup], str]:
        """Handle CV request logic"""
        # Admin bypass
        if user_id in ADMIN_USER_IDS:
            try:
                result = await send_email_with_cv(email, cv_type, user_id, self.supabase)
                return None, result
            except Exception as e:
                logger.error(f"Error sending CV for admin {user_id}: {str(e)}")
                return None, f"❌ Erreur: {str(e)}"

        # Check LinkedIn authentication
        if self.redis_client.get(REDIS_KEYS['AUTH_NEEDED']):
            await self.notify_admins_auth_needed(context, user_id)
            return None, (
                "⏳ Nous rencontrons un problème technique temporaire.\n"
                "Les administrateurs ont été notifiés et traiteront votre demande dès que possible.\n"
                "Veuillez réessayer dans quelques minutes."
            )

        # Check previous CV sends
        if await self.check_previous_cv(email, cv_type):
            return None, f'📩 Vous avez déjà reçu un CV de type {cv_type}.'

        # Generate and store verification data
        verification_code = self.generate_verification_code()
        await self.store_verification_data(user_id, email, cv_type, verification_code)
        
        # Create response markup
        keyboard = [
            [InlineKeyboardButton("📝 Voir la publication LinkedIn", url=LINKEDIN_POST_URL)],
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
        
        return reply_markup, instructions

    async def check_previous_cv(self, email: str, cv_type: str) -> bool:
        """Check if user has already received a CV"""
        try:
            response = self.supabase.table(SENT_EMAILS_TABLE)\
                .select('*')\
                .filter('email', 'eq', email)\
                .execute()

            return bool(response.data and response.data[0]['cv_type'] == cv_type)
        except Exception as e:
            logger.error(f"Error checking previous CV sends: {str(e)}")
            return False

    def generate_verification_code(self) -> str:
        """Generate random verification code"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=VERIFICATION_CODE_LENGTH))

    async def store_verification_data(
        self,
        user_id: int,
        email: str,
        cv_type: str,
        verification_code: str
    ) -> None:
        """Store verification data in Redis"""
        current_timestamp = str(int(datetime.utcnow().timestamp()))
        
        self.redis_client.setex(REDIS_KEYS['VERIFICATION_CODE'].format(user_id), 3600, verification_code)
        self.redis_client.setex(REDIS_KEYS['CODE_TIMESTAMP'].format(user_id), 3600, current_timestamp)
        self.redis_client.setex(REDIS_KEYS['EMAIL'].format(user_id), 3600, email)
        self.redis_client.setex(REDIS_KEYS['CV_TYPE'].format(user_id), 3600, cv_type)

    async def notify_admins_auth_needed(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
        """Notify admins that LinkedIn authentication is needed"""
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

    async def handle_linkedin_verification(
        self,
        query: Update.callback_query,
        user_id: int,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle LinkedIn verification process"""
        try:
            stored_data = await self.get_stored_verification_data(user_id)
            if not stored_data['code']:
                await query.message.edit_text("❌ Session expirée. Veuillez recommencer avec /sendcv")
                return
            
            verification_code = query.data.split("_")[1]
            if verification_code != stored_data['code']:
                await query.message.edit_text("❌ Code de vérification invalide. Veuillez recommencer avec /sendcv")
                return
            
            await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")
            
            verified, message = await self.verification_manager.verify_linkedin_comment(user_id)
            if not verified:
                await query.message.edit_text(message)
                return
            
            result = await send_email_with_cv(
                stored_data['email'],
                stored_data['cv_type'],
                user_id,
                self.supabase
            )
            
            await self.cleanup_verification_data(user_id)
            await query.message.edit_text(result)
            
        except Exception as e:
            logger.error(f"Error in LinkedIn verification: {str(e)}")
            await query.message.edit_text("❌ Une erreur s'est produite. Veuillez réessayer avec /sendcv")

    async def get_stored_verification_data(self, user_id: int) -> dict:
        """Retrieve stored verification data from Redis"""
        stored_code = self.redis_client.get(REDIS_KEYS['VERIFICATION_CODE'].format(user_id))
        stored_email = self.redis_client.get(REDIS_KEYS['EMAIL'].format(user_id))
        stored_cv_type = self.redis_client.get(REDIS_KEYS['CV_TYPE'].format(user_id))
        
        return {
            'code': stored_code.decode('utf-8') if stored_code else None,
            'email': stored_email.decode('utf-8') if stored_email else None,
            'cv_type': stored_cv_type.decode('utf-8') if stored_cv_type else None
        }

    async def cleanup_verification_data(self, user_id: int) -> None:
        """Clean up Redis verification data"""
        redis_keys = [
            REDIS_KEYS['VERIFICATION_CODE'].format(user_id),
            REDIS_KEYS['CODE_TIMESTAMP'].format(user_id),
            REDIS_KEYS['EMAIL'].format(user_id),
            REDIS_KEYS['CV_TYPE'].format(user_id)
        ]
        self.redis_client.delete(*redis_keys)

    @private_chat_only
    async def my_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /myid command"""
        user_id = update.effective_user.id
        await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        try:
            await query.answer()
            
            if query.data.startswith("verify_"):
                await self.handle_linkedin_verification(query, user_id, context)
            
        except Exception as e:
            logger.error(f"Error in callback handler: {str(e)}")
            await query.message.edit_text("❌ Une erreur s'est produite. Veuillez réessayer.")

def setup_handlers(application, handler_instance: UserCommandHandler):
    """Set up all command handlers"""
    # Command handlers
    application.add_handler(CommandHandler("start", handler_instance.start))
    application.add_handler(CommandHandler("sendcv", handler_instance.send_cv))
    application.add_handler(CommandHandler("myid", handler_instance.my_id))
    application.add_handler(CommandHandler("admin_auth", handler_instance.admin_auth))
    application.add_handler(CommandHandler("auth_callback", handler_instance.auth_callback))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(handler_instance.callback_handler))

def initialize_handlers(redis_client, supabase_client):
    """Initialize handler instance"""
    return UserCommandHandler(redis_client, supabase_client)
