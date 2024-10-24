import re
import logging
import random
import string
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any, List
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    Application
)
from telegram.error import TelegramError
from redis.exceptions import RedisError

import redis
from supabase import create_client, Client

from utils.linkedin_utils import (
    LinkedInVerificationManager,
    LinkedInTokenManager,
    LinkedInConfig,
    LinkedInError,
    LinkedInErrorCode
)
from utils.email_utils import send_email_with_cv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CommandError(Exception):
    """Custom exception for command handling errors"""
    pass

def private_chat_only(func):
    """Decorator to restrict commands to private chats only"""
    @wraps(func)
    async def wrapped(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "❌ Cette commande n'est disponible qu'en message privé."
            )
            return
        return await func(self, update, context)
    return wrapped

class RedisKeys:
    """Redis key constants"""
    VERIFICATION_CODE = 'linkedin_verification_code:{}'
    CODE_TIMESTAMP = 'linkedin_code_timestamp:{}'
    EMAIL = 'linkedin_email:{}'
    CV_TYPE = 'linkedin_cv_type:{}'
    RATE_LIMIT = 'rate_limit:{}:{}'

class UserCommandHandler:
    ADMIN_IDS = [1719899525, 987654321]  # Add your actual admin user IDs here
        
    # Add rate limiting constants
    MAX_ATTEMPTS = 5  # Maximum number of attempts allowed
    RATE_LIMIT_WINDOW = 60 * 60  # Time window in seconds (1 hour)
    def __init__(
        self,
        redis_client: redis.Redis,
        supabase_client: Client,
        linkedin_config: LinkedInConfig,
        linkedin_token_manager: LinkedInTokenManager,
        linkedin_verification_manager: LinkedInVerificationManager  # Match the name being passed
    ):
        self.redis_client = redis_client
        self.supabase = supabase_client
        self.linkedin_config = linkedin_config
        self.linkedin_token_manager = linkedin_token_manager
        self.verification_manager = linkedin_verification_manager 

    async def handle_telegram_error(self, message: Message, error: TelegramError):
        """Handle errors coming from Telegram API"""
        await message.reply_text("⚠️ Une erreur s'est produite avec Telegram. Veuillez réessayer.")
        logger.error(f"TelegramError: {error}")

    async def handle_generic_error(self, message: Message):
        """Handle generic errors during command execution"""
        await message.reply_text("❌ Une erreur inattendue est survenue. Veuillez réessayer plus tard.")

    async def check_rate_limit(self, user_id: int, command: str) -> bool:
        """Check if user has exceeded rate limit for a command"""
        if user_id in self.ADMIN_IDS:
            return True
        
        key = RedisKeys.RATE_LIMIT.format(user_id, command)
        attempts = self.redis_client.get(key)
        
        if attempts and int(attempts) >= self.MAX_ATTEMPTS:
            return False
        self.redis_client.expire(key, self.RATE_LIMIT_WINDOW)

        if not attempts:
            self.redis_client.expire(key, self.rate_limit_window)
        
        return True

    @private_chat_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        try:
            user_id = update.effective_user.id
            if not await self.check_rate_limit(user_id, 'start'):
                await update.message.reply_text(
                    "⚠️ Vous avez atteint la limite de commandes. "
                    "Veuillez réessayer plus tard."
                )
                return

            welcome_message = (
                '👋 Bonjour ! Voici les commandes disponibles :\n\n'
                '/sendcv - Recevoir un CV\n'
                '/myid - Voir votre ID\n\n'
                '📄 Pour recevoir un CV, vous devrez :\n'
                '1. Fournir votre email\n'
                '2. Choisir le type de CV (junior/senior)\n'
                '3. Commenter sur notre publication LinkedIn'
            )
            await update.message.reply_text(welcome_message)
            logger.info(f"Start command completed for user {user_id}")
            
        except TelegramError as e:
            logger.error(f"Telegram error in start command: {str(e)}")
            await self.handle_telegram_error(update.message, e)
        except Exception as e:
            logger.error(f"Error in start command: {str(e)}")
            await self.handle_generic_error(update.message)

    def is_valid_email(self, email: str) -> bool:
        """Simple email format validation"""
        
        regex = r'^\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return re.match(regex, email) is not None

    @private_chat_only
    async def send_cv(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /sendcv command"""
        try:
            user_id = update.effective_user.id
            is_admin = user_id in self.ADMIN_IDS
            
            if not is_admin and not await self.check_rate_limit(user_id, 'sendcv'):
                await update.message.reply_text(
                    "⚠️ Vous avez atteint la limite de demandes de CV. "
                    "Veuillez réessayer dans 1 heure."
                )
                return
            
            if len(context.args) != 2:
                raise CommandError(
                    '❌ Format incorrect. Utilisez:\n'
                    '/sendcv [email] [junior|senior]\n'
                    'Exemple: /sendcv email@example.com junior'
                )
            
            email, cv_type = context.args
            cv_type = cv_type.lower()
            
            if cv_type not in ['junior', 'senior']:
                raise CommandError('❌ Type de CV incorrect. Utilisez "junior" ou "senior".')
            
            if not self.is_valid_email(email):
                raise CommandError("❌ Format d'email invalide.")
    
            if not is_admin and self.check_previous_cv(email, cv_type):
                raise CommandError(f'📩 Vous avez déjà reçu un CV de type {cv_type}.')
                
            result = await self.handle_cv_request(update, context, user_id, email, cv_type)
            await update.message.reply_text(
                result[1],
                reply_markup=result[0] if result[0] else None
            )
                
        except CommandError as e:
            await update.message.reply_text(str(e))
        except TelegramError as e:
            logger.error(f"Telegram error in send_cv command: {str(e)}")
            await self.handle_telegram_error(update.message, e)
        except Exception as e:
            logger.error(f"Error in send_cv command: {str(e)}")
            await self.handle_generic_error(update.message)

    def check_previous_cv(self, email: str, cv_type: str) -> bool:
        """Check if user has already received a CV"""
        try:
            response = self.supabase.table('sent_emails')\
                .select('*')\
                .eq('email', email)\
                .eq('cv_type', cv_type)\
                .execute()
            
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error checking previous CV sends: {str(e)}")
            return False

    async def handle_cv_request(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        email: str,
        cv_type: str
    ) -> Tuple[Optional[InlineKeyboardMarkup], str]:
        """Handle CV request logic with improved error handling"""
        try:
            verification_code = self.generate_verification_code()
            await self.store_verification_data(user_id, email, cv_type, verification_code)
            
            keyboard = [
                [InlineKeyboardButton(
                    "📝 Voir la publication LinkedIn",
                    url=self.linkedin_config.post_url
                )],
                [InlineKeyboardButton(
                    "✅ J'ai commenté",
                    callback_data=f"verify_{verification_code}"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            instructions = self.generate_instructions_message(verification_code)
            return reply_markup, instructions
        
        except CommandError as e:
            raise
        except Exception as e:
            logger.error(f"Error in handle_cv_request: {str(e)}")
            raise CommandError("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")

    def generate_verification_code(self, length: int = 6) -> str:
        """Generate random verification code"""
        return ''.join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=length
            )
        )

    async def handle_linkedin_verification(
        self,
        query: Update.callback_query,
        user_id: int,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle LinkedIn verification process with improved error handling"""
        try:
            # Get verification code from callback data
            verification_code = query.data.split("_")[1]
    
            # Get stored verification data
            stored_data = await self.get_stored_verification_data(user_id)
            
            # Check if verification data exists
            if not all(stored_data.values()):
                await query.message.edit_text(
                    "❌ Session expirée. Veuillez recommencer avec /sendcv"
                )
                return
    
            # Store verification code in Redis for the verification manager
            await self.redis_client.set(
                f"linkedin_verification_code:{user_id}",
                verification_code,
                ex=3600  # 1 hour expiry
            )
    
            await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")
    
            # Verify the LinkedIn comment
            verified, message = await self.verification_manager.verify_linkedin_comment(user_id)
    
            if verified:
                # Send CV if verification successful
                result = await send_email_with_cv(
                    stored_data['email'],
                    stored_data['cv_type'],
                    user_id,
                    self.supabase
                )
                
                # Clean up all verification data
                await self.cleanup_verification_data(user_id)
                
                # Update message with result
                await query.message.edit_text(result)
            else:
                await query.message.edit_text(message)
    
        except RedisError as e:
            logger.error(f"Redis error in verification process: {str(e)}")
            await query.message.edit_text(
                "❌ Erreur de stockage temporaire. Veuillez réessayer avec /sendcv"
            )
        except LinkedInError as e:
            logger.error(f"LinkedIn error in verification process: {str(e)}")
            await query.message.edit_text(
                "❌ Erreur de connexion à LinkedIn. Veuillez réessayer plus tard."
            )
        except TelegramError as e:
            logger.error(f"Telegram error in verification process: {str(e)}")
            await self.handle_telegram_error(query.message, e)
        except Exception as e:
            logger.error(f"Unexpected error in verification process: {str(e)}")
            await self.handle_generic_error(query.message)
            
    async def store_verification_data(
        self,
        user_id: int,
        email: str,
        cv_type: str,
        verification_code: str
    ) -> None:
        """Store verification data in Redis"""
        try:
            current_timestamp = str(int(datetime.utcnow().timestamp()))
            expiry_time = 3600  # 1 hour
            
            pipeline = self.redis_client.pipeline()
            
            pipeline.setex(
                RedisKeys.VERIFICATION_CODE.format(user_id),
                expiry_time,
                verification_code
            )
            pipeline.setex(
                RedisKeys.CODE_TIMESTAMP.format(user_id),
                expiry_time,
                current_timestamp
            )
            pipeline.setex(
                RedisKeys.EMAIL.format(user_id),
                expiry_time,
                email
            )
            pipeline.setex(
                RedisKeys.CV_TYPE.format(user_id),
                expiry_time,
                cv_type
            )
            
            pipeline.execute()
            
        except Exception as e:
            logger.error(f"Error storing verification data: {str(e)}")
            raise CommandError("❌ Erreur lors du stockage des données. Veuillez réessayer.")

    async def get_stored_verification_data(self, user_id: int) -> Dict[str, Optional[str]]:
        """Retrieve stored verification data from Redis"""
        try:
            pipeline = self.redis_client.pipeline()
    
            pipeline.get(RedisKeys.VERIFICATION_CODE.format(user_id))
            pipeline.get(RedisKeys.EMAIL.format(user_id))
            pipeline.get(RedisKeys.CV_TYPE.format(user_id))
            
            values = pipeline.execute()
            
            return {
                'code': values[0].decode('utf-8') if values[0] else None,
                'email': values[1].decode('utf-8') if values[1] else None,
                'cv_type': values[2].decode('utf-8') if values[2] else None
            }
        except Exception as e:
            logger.error(f"Error retrieving verification data: {str(e)}")
            return {'code': None, 'email': None, 'cv_type': None}

    async def cleanup_verification_data(self, user_id: int) -> None:
        """Clean up Redis verification data"""
        try:
            pipeline = self.redis_client.pipeline()
            keys = [
                RedisKeys.VERIFICATION_CODE.format(user_id),
                RedisKeys.CODE_TIMESTAMP.format(user_id),
                RedisKeys.EMAIL.format(user_id),
                RedisKeys.CV_TYPE.format(user_id)
            ]
            pipeline.delete(*keys)
            
            pipeline.execute()
        except Exception as e:
            logger.error(f"Error cleaning up verification data: {str(e)}")

    @private_chat_only
    async def my_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /myid command"""
        try:
            user_id = update.effective_user.id
            if not await self.check_rate_limit(user_id, 'myid'):
                await update.message.reply_text(
                    "⚠️ Vous avez atteint la limite de commandes. "
                    "Veuillez réessayer plus tard."
                )
                return
                
            await update.message.reply_text(f'🔍 Votre ID est : {user_id}')
            
        except TelegramError as e:
            logger.error(f"Telegram error in my_id command: {str(e)}")
            await self.handle_telegram_error(update.message, e)
        except Exception as e:
            logger.error(f"Error in my_id command: {str(e)}")
            await self.handle_generic_error(update.message)

    async def callback_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle callback queries with improved error handling"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        try:
            await query.answer()
            
            if not await self.check_rate_limit(user_id, 'callback'):
                await query.message.edit_text(
                    "⚠️ Vous avez atteint la limite de vérifications. "
                    "Veuillez réessayer plus tard."
                )
                return
            
            if query.data.startswith("verify_"):
                await self.handle_linkedin_verification(query, user_id, context)
            else:
                logger.warning(f"Unknown callback data: {query.data}")
                await query.message.edit_text("❌ Action invalide.")
            
        except TelegramError as e:
            logger.error(f"Telegram error in callback handler: {str(e)}")
            await self.handle_telegram_error(query.message, e)
        except Exception as e:
            logger.error(f"Error in callback handler: {str(e)}")
            await self.handle_generic_error(query.message)

    async def handle_telegram_error(self, message: Message, error: TelegramError) -> None:
        """Handle Telegram-specific errors"""
        try:
            if isinstance(error, TelegramError):
                if "Message is not modified" in str(error):
                    logger.warning("Attempted to edit message with same content")
                    return
                elif "Message to edit not found" in str(error):
                    await message.reply_text(
                        "❌ Message expiré. Veuillez réessayer la commande."
                    )
                else:
                    await message.reply_text(
                        "❌ Une erreur de communication s'est produite. "
                        "Veuillez réessayer plus tard."
                    )
        except Exception as e:
            logger.error(f"Error in handle_telegram_error: {str(e)}")

    async def handle_generic_error(self, message: Message) -> None:
        """Handle general errors with user-friendly messages"""
        try:
            await message.reply_text(
                "❌ Une erreur inattendue s'est produite. "
                "Veuillez réessayer plus tard."
            )
        except Exception as e:
            logger.error(f"Error in handle_generic_error: {str(e)}")

    def generate_instructions_message(self, verification_code: str) -> str:
        """Generate instructions message for LinkedIn verification"""
        return (
            f"📝 Pour recevoir votre CV, veuillez :\n\n"
            f"1. Cliquer sur le lien vers la publication LinkedIn\n"
            f"2. Commenter avec le code : {verification_code}\n"
            f"3. Revenir ici et cliquer sur 'J'ai commenté'\n\n"
            f"⏳ Ce code est valable pendant 1 heure."
        )

    @staticmethod
    def is_valid_email(email: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def setup_handlers(self, application: Application) -> None:
        """Register all command and callback handlers"""
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("sendcv", self.send_cv))
        application.add_handler(CommandHandler("myid", self.my_id))
        application.add_handler(CallbackQueryHandler(self.callback_handler))
