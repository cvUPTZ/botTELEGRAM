import re
import logging
from datetime import datetime
from typing import Tuple, Optional, Dict
from functools import wraps

from telegram import Update, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes, CommandHandler, Application
from telegram.error import TelegramError
from redis.exceptions import RedisError

import redis
from supabase import Client

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
    RATE_LIMIT = 'rate_limit:{}:{}'


class UserCommandHandler:
    ADMIN_IDS = [1719899525, 987654321]
    MAX_ATTEMPTS = 5
    RATE_LIMIT_WINDOW = 60 * 60  # 1 hour in seconds

    def __init__(self, redis_client: redis.Redis, supabase_client: Client):
        self.redis_client = redis_client
        self.supabase = supabase_client

        # Test Redis connection on initialization
        try:
            self.redis_client.ping()
        except RedisError as e:
            logger.error(f"Redis connection failed during initialization: {str(e)}")

    async def test_redis_connection(self) -> bool:
        """Test if Redis connection is working"""
        try:
            self.redis_client.ping()
            return True
        except RedisError as e:
            logger.error(f"Redis connection test failed: {str(e)}")
            return False

    async def handle_telegram_error(self, message: Message, error: TelegramError):
        """Handle errors coming from Telegram API"""
        await message.reply_text("⚠️ Une erreur s'est produite avec Telegram. Veuillez réessayer.")
        logger.error(f"TelegramError: {error}")

    async def handle_generic_error(self, message: Message):
        """Handle generic errors during command execution"""
        await message.reply_text("❌ Une erreur inattendue est survenue. Veuillez réessayer plus tard.")

    async def check_rate_limit(self, user_id: int, command: str) -> bool:
        """Check if user has exceeded rate limit for a command"""
        try:
            if user_id in self.ADMIN_IDS:
                return True

            if not await self.test_redis_connection():
                logger.warning("Redis unavailable for rate limiting - allowing request")
                return True

            key = RedisKeys.RATE_LIMIT.format(user_id, command)
            attempts = self.redis_client.get(key)

            if attempts is None:
                self.redis_client.setex(key, self.RATE_LIMIT_WINDOW, 1)
                return True

            attempts = int(attempts)
            if attempts >= self.MAX_ATTEMPTS:
                return False

            self.redis_client.incr(key)
            return True

        except RedisError as e:
            logger.error(f"Redis error checking rate limit: {str(e)}")
            return True
        except Exception as e:
            logger.error(f"Error checking rate limit: {str(e)}")
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
                '2. Choisir le type de CV (junior/senior)'
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
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

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
            # Sending email logic
            return None, "✅ Votre CV a été envoyé avec succès !"

        except RedisError as e:
            logger.error(f"Redis error in handle_cv_request: {str(e)}")
            raise CommandError("⚠️ Service temporairement indisponible. Veuillez réessayer plus tard.")
        except Exception as e:
            logger.error(f"Error in handle_cv_request: {str(e)}")
            raise CommandError("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")
