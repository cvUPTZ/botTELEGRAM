import logging
import random
import string
from datetime import datetime
from typing import Tuple, Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from utils.decorators import private_chat_only
from utils.email_utils import send_email_with_cv
from config import (
    ADMIN_USER_IDS,
    SENT_EMAILS_TABLE,
    VERIFICATION_CODE_LENGTH,
    LINKEDIN_POST_URL,
    LINKEDIN_POST_ID,
    API_TIMEOUT_SECONDS
)

import aiohttp
import asyncio
import redis
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis key constants
REDIS_KEYS = {
    'VERIFICATION_CODE': 'linkedin_verification_code:{}',
    'CODE_TIMESTAMP': 'linkedin_code_timestamp:{}',
    'EMAIL': 'linkedin_email:{}',
    'CV_TYPE': 'linkedin_cv_type:{}'
}

class LinkedInVerificationManager:
    """Handle LinkedIn verification process with simplified code matching"""
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    async def verify_linkedin_comment(self, user_id: str) -> Tuple[bool, str]:
        """Verify if a user has commented on the LinkedIn post with their verification code"""
        try:
            stored_code = self.redis_client.get(REDIS_KEYS['VERIFICATION_CODE'].format(user_id))
            if not stored_code:
                return False, "Code de vérification non trouvé. Veuillez recommencer."

            stored_code = stored_code.decode('utf-8')
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": "202304"
                }

                try:
                    async with session.get(
                        f"https://api.linkedin.com/v2/socialActions/{LINKEDIN_POST_ID}/comments",
                        headers=headers,
                        timeout=API_TIMEOUT_SECONDS
                    ) as response:
                        if response.status != 200:
                            logger.error("LinkedIn API error", extra={
                                'status_code': response.status,
                                'user_id': user_id,
                                'endpoint': 'comments'
                            })
                            return False, "Erreur de connexion à LinkedIn. Veuillez réessayer plus tard."

                        data = await response.json()
                        return await self.process_comments(data, stored_code, user_id)

                except asyncio.TimeoutError:
                    logger.error("LinkedIn API timeout")
                    return False, "Délai d'attente dépassé. Veuillez réessayer plus tard."

                except aiohttp.ClientError as e:
                    logger.error(f"Network error: {str(e)}")
                    return False, "Erreur de connexion réseau. Veuillez réessayer plus tard."

        except Exception as e:
            logger.error(f"Error verifying LinkedIn comment: {str(e)}")
            return False, "Erreur technique. Veuillez réessayer plus tard."

    async def process_comments(self, data: Dict[str, Any], stored_code: str, user_id: str) -> Tuple[bool, str]:
        """Process LinkedIn comments to find verification code"""
        comments = data.get('elements', [])
        if not comments:
            return False, "Aucun commentaire trouvé. Assurez-vous d'avoir commenté avec le code fourni."

        code_timestamp = self.redis_client.get(REDIS_KEYS['CODE_TIMESTAMP'].format(user_id))
        if not code_timestamp:
            return False, "Session expirée. Veuillez recommencer."

        code_timestamp = float(code_timestamp.decode('utf-8'))

        for comment in comments:
            comment_text = comment.get('message', {}).get('text', '').strip()
            comment_time = int(comment.get('created', {}).get('time', 0)) / 1000

            if stored_code == comment_text and comment_time > code_timestamp:
                logger.info(f"Valid comment found for user {user_id}")
                return True, "Vérification réussie!"

        return False, "Code de vérification non trouvé dans les commentaires. Assurez-vous d'avoir copié exactement le code fourni."

class UserCommandHandler:
    """Handle user commands and interactions"""
    def __init__(self, redis_client, supabase_client):
        self.redis_client = redis_client
        self.supabase = supabase_client
        self.verification_manager = LinkedInVerificationManager(redis_client)

    @private_chat_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        logger.info(f"Start command received from user {update.effective_user.id}")
        try:
            await update.message.reply_text(
                '👋 Bonjour ! Voici les commandes disponibles :\n\n'
                '/sendcv - Recevoir un CV\n'
                '/myid - Voir votre ID\n\n'
                '📄 Pour recevoir un CV, vous devrez commenter sur notre publication LinkedIn !'
            )
            logger.info("Start message sent successfully")
        except Exception as e:
            logger.error(f"Error sending start message: {str(e)}")
            await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")

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
        """Handle CV request logic with simplified verification"""
        try:
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
            
            # Prepare instructions message
            instructions = (
                f"Pour recevoir votre CV, veuillez suivre ces étapes:\n\n"
                f"1. Cliquer sur le bouton ci-dessous pour voir la publication\n"
                f"2. Commenter avec exactement ce code : {verification_code}\n"
                f"3. Revenir ici et cliquer sur 'J'ai commenté'\n\n"
                f"⚠️ Important:\n"
                f"- Le code est valide pendant 1 heure\n"
                f"- Les commentaires faits avant la génération du code ne sont pas valides\n"
                f"- Un seul CV par adresse email"
            )
            
            return reply_markup, instructions

        except Exception as e:
            logger.error(f"Error in handle_cv_request: {str(e)}")
            return None, "❌ Une erreur s'est produite. Veuillez réessayer plus tard."

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
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(handler_instance.callback_handler))

def initialize_handlers(redis_client, supabase_client):
    """Initialize handler instance"""
    return UserCommandHandler(redis_client, supabase_client)
