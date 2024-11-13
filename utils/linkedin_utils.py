import logging
import aiohttp
import asyncio
import secrets
from typing import Optional, Tuple, Dict, Any
from redis import Redis

from datetime import datetime, timedelta
from redis.asyncio import Redis
from redis.exceptions import RedisError

import tempfile
import os


from urllib.parse import quote
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LinkedInError(Exception):
    """Custom exception for LinkedIn API errors."""
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

class LinkedInErrorCode:
    """Error codes for LinkedIn API."""
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_REQUEST = "INVALID_REQUEST"
    API_ERROR = "API_ERROR"
    REDIS_ERROR = "REDIS_ERROR"

class LinkedInConfig:
    """Configuration class for LinkedIn integration."""
    def __init__(self, 
                 client_id: str, 
                 client_secret: str, 
                 redirect_uri: str, 
                 post_url: str,
                 access_token: str, 
                 scope: str, 
                 company_page_id: int, 
                 post_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.post_url = post_url
        self.access_token = access_token
        self.scope = scope
        self.company_page_id = company_page_id
        self.post_id = post_id

class LinkedInTokenManager:
    """Manage LinkedIn access tokens."""
    
    def __init__(self, redis_client: Optional[Redis], config: LinkedInConfig):
        self.redis = redis_client
        self.config = config
        self.token_key_prefix = "linkedin_token:"
        self.token_expiry_prefix = "linkedin_token_expiry:"
        self.refresh_token_prefix = "linkedin_refresh_token:"

    async def _ensure_redis_connection(self) -> None:
        """Ensure Redis connection is available."""
        if self.redis is None:
            raise LinkedInError("Redis client not initialized", LinkedInErrorCode.REDIS_ERROR)
        try:
            await self.redis.ping()
        except (RedisError, AttributeError) as e:
            logger.error(f"Redis connection error: {str(e)}")
            raise LinkedInError("Redis connection failed", LinkedInErrorCode.REDIS_ERROR)

    async def get_token(self, user_id: int) -> Optional[str]:
        """Get valid access token for user."""
        try:
            await self._ensure_redis_connection()
            
            token = await self.redis.get(f"{self.token_key_prefix}{user_id}")
            if not token:
                return None

            expiry = await self.redis.get(f"{self.token_expiry_prefix}{user_id}")
            if not expiry or float(expiry.decode('utf-8')) < datetime.utcnow().timestamp():
                return None

            return token.decode('utf-8')
        
        except LinkedInError:
            raise
        except Exception as e:
            logger.error(f"Error getting token for user {user_id}: {str(e)}")
            return None

    async def store_token(self, user_id: int, access_token: str, expires_in: int, refresh_token: Optional[str] = None) -> None:
        """Store access token and optionally refresh token with expiry."""
        try:
            await self._ensure_redis_connection()
            
            expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            pipeline = self.redis.pipeline()
            
            # Store access token
            pipeline.setex(f"{self.token_key_prefix}{user_id}", expires_in, access_token)
            pipeline.setex(f"{self.token_expiry_prefix}{user_id}", expires_in, expiry.timestamp())
            
            # Store refresh token if provided
            if refresh_token:
                pipeline.set(f"{self.refresh_token_prefix}{user_id}", refresh_token)
            
            await pipeline.execute()
        
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error storing token for user {user_id}: {str(e)}")
            raise LinkedInError("Failed to store token", LinkedInErrorCode.REDIS_ERROR)

    async def refresh_token(self, user_id: int) -> Optional[str]:
        """Refresh expired access token."""
        try:
            await self._ensure_redis_connection()
            refresh_token = await self.get_refresh_token(user_id)
            
            if not refresh_token:
                logger.error(f"No refresh token found for user {user_id}")
                return None

            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'refresh_token',
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret,
                    'refresh_token': refresh_token
                }
                
                async with session.post('https://www.linkedin.com/oauth/v2/accessToken', data=data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Token refresh failed: {error_text}")
                        raise LinkedInError("Failed to refresh token", LinkedInErrorCode.TOKEN_EXPIRED)
                    
                    result = await response.json()
                    new_access_token = result.get('access_token')
                    new_refresh_token = result.get('refresh_token')
                    expires_in = result.get('expires_in', 3600)
                    
                    await self.store_token(
                        user_id, 
                        new_access_token, 
                        expires_in,
                        new_refresh_token
                    )
                    return new_access_token
                    
        except LinkedInError:
            raise
        except Exception as e:
            logger.error(f"Error refreshing token for user {user_id}: {str(e)}")
            return None

    async def get_refresh_token(self, user_id: int) -> Optional[str]:
        """Get refresh token for user."""
        try:
            await self._ensure_redis_connection()
            token = await self.redis.get(f"{self.refresh_token_prefix}{user_id}")
            return token.decode('utf-8') if token else None
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error getting refresh token for user {user_id}: {str(e)}")
            return None



class LinkedInAPI:
    """Class to handle LinkedIn API interactions"""
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.linkedin.com/v2"
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json'
        }

    async def get_post_comments(self, post_id: str) -> list:
        """
        Fetch comments on a LinkedIn post asynchronously.
        
        Args:
            post_id (str): The URN of the LinkedIn post
            
        Returns:
            list: List of comment texts or empty list if failed
        """
        try:
            encoded_post_id = quote(post_id, safe='')
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/socialActions/{encoded_post_id}/comments",
                    headers=self.headers
                ) as response:
                    if response.status != 200:
                        logger.error(f"Error fetching comments: {await response.text()}")
                        return []
                    
                    comments_data = await response.json()
                    comments = comments_data.get('elements', [])
                    return [comment.get('message', {}).get('text', '') 
                           for comment in comments]
                    
        except Exception as e:
            logger.error(f"Error fetching comments: {str(e)}")
            return []

class LinkedInVerificationManager:
    """Manage LinkedIn comment verification process using LinkedIn API."""
    
    def __init__(self, 
                 redis_client: Optional[Redis], 
                 token_manager: 'LinkedInTokenManager', 
                 config: 'LinkedInConfig', 
                 verification_ttl: int = 3600):
        self.redis = redis_client
        self.token_manager = token_manager
        self.config = config
        self.verification_ttl = verification_ttl
        self.verification_code_prefix = "linkedin_verification_code:"
        self.linkedin_api = LinkedInAPI(config.access_token)

    async def verify_linkedin_comment(self, user_id: int, verification_code: str) -> Tuple[bool, str]:
        """Verify user's LinkedIn comment using LinkedIn API."""
        try:
            # Get verification code from Redis
            stored_code = await self.redis.get(f"{self.verification_code_prefix}{user_id}")
            if not stored_code:
                return False, "❌ Code de vérification expiré ou introuvable."
            
            stored_code = stored_code.decode('utf-8')
            
            # Fetch comments from LinkedIn API
            comments = await self.linkedin_api.get_post_comments(self.config.post_id)
            
            # Check if verification code exists in any comment
            code_found = False
            for comment in comments:
                if stored_code in comment:
                    code_found = True
                    break
            
            if code_found:
                await self._cleanup_verification_data(user_id)
                return True, "✅ Code vérifié avec succès! Envoi du CV en cours..."
            else:
                return False, "❌ Code de vérification non trouvé dans les commentaires. Assurez-vous d'avoir commenté avec le bon code."
                    
        except RedisError as e:
            logger.error(f"Redis error during verification: {str(e)}")
            return False, "❌ Erreur lors de la vérification du code."
        except Exception as e:
            logger.error(f"Error during verification: {str(e)}")
            return False, "❌ Une erreur s'est produite lors de la vérification."

    async def _cleanup_verification_data(self, user_id: int) -> None:
        """Clean up verification data from Redis."""
        try:
            await self.redis.delete(f"{self.verification_code_prefix}{user_id}")
        except RedisError as e:
            logger.error(f"Error during cleanup: {str(e)}")







class LinkedInAuthManager:
    """Manage LinkedIn OAuth authentication process."""
    
    def __init__(self, 
                 redis_client: Optional[Redis], 
                 token_manager: LinkedInTokenManager, 
                 config: LinkedInConfig):
        self.redis = redis_client
        self.token_manager = token_manager
        self.config = config
        self.state_prefix = "linkedin_auth_state:"
        self.state_ttl = 600  # 10 minutes

    async def _ensure_redis_connection(self) -> None:
        """Ensure Redis connection is available."""
        if self.redis is None:
            raise LinkedInError("Redis client not initialized", LinkedInErrorCode.REDIS_ERROR)
        try:
            await self.redis.ping()
        except (RedisError, AttributeError) as e:
            logger.error(f"Redis connection error: {str(e)}")
            raise LinkedInError("Redis connection failed", LinkedInErrorCode.REDIS_ERROR)

    async def generate_auth_url(self, user_id: int) -> str:
        """Generate LinkedIn OAuth authorization URL."""
        try:
            await self._ensure_redis_connection()
            
            # Generate state parameter for CSRF protection
            state = secrets.token_urlsafe(32)
            
            # Store state with user_id
            await self.redis.setex(
                f"{self.state_prefix}{state}",
                self.state_ttl,
                str(user_id)
            )
            
            # Build authorization URL
            params = {
                'response_type': 'code',
                'client_id': self.config.client_id,
                'redirect_uri': self.config.redirect_uri,
                'state': state,
                'scope': self.config.scope
            }
            
            query_string = '&'.join(f"{k}={v}" for k, v in params.items())
            return f"https://www.linkedin.com/oauth/v2/authorization?{query_string}"
            
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error generating auth URL: {str(e)}")
            raise LinkedInError("Failed to generate authorization URL", LinkedInErrorCode.REDIS_ERROR)

    async def validate_state(self, state: str) -> Optional[int]:
        """Validate state parameter and return associated user_id."""
        try:
            await self._ensure_redis_connection()
            
            user_id = await self.redis.get(f"{self.state_prefix}{state}")
            if not user_id:
                return None
            
            # Clean up used state
            await self.redis.delete(f"{self.state_prefix}{state}")
            
            return int(user_id.decode('utf-8'))
            
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error validating state: {str(e)}")
            return None

    async def handle_oauth_callback(self, code: str, state: str) -> Tuple[bool, str, Optional[int]]:
        """Handle OAuth callback and exchange code for tokens."""
        try:
            # Validate state parameter
            user_id = await self.validate_state(state)
            if not user_id:
                return False, "❌ Session invalide ou expirée.", None

            # Exchange code for tokens
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret,
                    'redirect_uri': self.config.redirect_uri
                }
                
                async with session.post('https://www.linkedin.com/oauth/v2/accessToken', data=data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Token exchange failed: {error_text}")
                        return False, "❌ Échec de l'authentification LinkedIn.", user_id
                    
                    result = await response.json()
                    
                    # Store tokens
                    await self.token_manager.store_token(
                        user_id=user_id,
                        access_token=result['access_token'],
                        expires_in=result['expires_in'],
                        refresh_token=result.get('refresh_token')
                    )
                    
                    return True, "✅ Authentification LinkedIn réussie!", user_id
                    
        except LinkedInError as e:
            logger.error(f"LinkedIn error during OAuth callback: {str(e)}")
            return False, self._get_user_friendly_error_message(e), None
        except Exception as e:
            logger.error(f"Unexpected error during OAuth callback: {str(e)}")
            return False, "❌ Une erreur inattendue s'est produite.", None

def create_linkedin_managers(redis_url: str, config: LinkedInConfig) -> Tuple[LinkedInTokenManager, LinkedInVerificationManager, LinkedInAuthManager]:
    """Create and initialize all LinkedIn managers."""
    try:
        # Initialize Redis client
        redis_client = Redis.from_url(redis_url)
        
        # Initialize managers
        token_manager = LinkedInTokenManager(redis_client, config)
        verification_manager = LinkedInVerificationManager(redis_client, token_manager, config)
        auth_manager = LinkedInAuthManager(redis_client, token_manager, config)
        
        return token_manager, verification_manager, auth_manager
        
    except Exception as e:
        logger.error(f"Error initializing LinkedIn managers: {str(e)}")
        raise


    # # Modified handle_linkedin_verification method for UserCommandHandler
    # async def handle_linkedin_verification(
    #     self,
    #     query: Update.callback_query,
    #     user_id: int,
    #     context: ContextTypes.DEFAULT_TYPE
    # ) -> None:
    #     """Handle LinkedIn verification process with temp file."""
    #     try:
    #         verification_code = query.data.split("_")[1]
            
    #         # Store verification code in Redis
    #         await self.redis_client.set(
    #             f"linkedin_verification_code:{user_id}",
    #             verification_code,
    #             ex=3600  # 1 hour expiry
    #         )
            
    #         await query.message.edit_text("🔄 Vérification du code en cours...")
            
    #         # Verify code using temp file
    #         verified, message = await self.verification_manager.verify_linkedin_comment(user_id)
            
    #         if verified:
    #             # Get email and CV type from Redis
    #             stored_data = await self.get_stored_verification_data(user_id)
    #             if not all(stored_data.values()):
    #                 await query.message.edit_text(
    #                     "❌ Données de demande expirées. Veuillez recommencer avec /sendcv"
    #                 )
    #                 return
                    
    #             # Send CV
    #             result = await send_email_with_cv(
    #                 stored_data['email'],
    #                 stored_data['cv_type'],
    #                 user_id,
    #                 self.supabase
    #             )
                
    #             await self.cleanup_verification_data(user_id)
    #             await query.message.edit_text(result)
    #         else:
    #             await query.message.edit_text(message)
                
    #     except Exception as e:
    #         logger.error(f"Error in verification process: {str(e)}")
    #         await query.message.edit_text(
    #             "❌ Une erreur s'est produite. Veuillez réessayer avec /sendcv"
    #         )


# # linkedin_utils.py
# import logging
# import aiohttp
# import redis.asyncio as redis
# from typing import Optional, Dict, Tuple
# from datetime import datetime
# import asyncio

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
# )
# logger = logging.getLogger(__name__)

# class LinkedInConfig:
#     def __init__(self, client_id: str, client_secret: str, redirect_uri: str, post_url: str):
#         self.client_id = client_id
#         self.client_secret = client_secret
#         self.redirect_uri = redirect_uri
#         self.post_url = post_url

# class LinkedInManager:
#     def __init__(self, redis_client: redis.Redis, config: LinkedInConfig):
#         self.redis = redis_client
#         self.config = config
#         self.token_prefix = "linkedin_token:"
#         self.verification_prefix = "linkedin_verify:"
#         self.retry_prefix = "linkedin_retry:"
#         self.max_retries = 3
#         self.retry_expiry = 86400  # 24 hours

#     async def get_access_token(self, user_id: int) -> Optional[str]:
#         """Get valid access token for user"""
#         try:
#             key = f"{self.token_prefix}{user_id}"
#             token = await self.redis.get(key)
#             return token.decode('utf-8') if token else None
#         except Exception as e:
#             logger.error(f"Error getting token: {str(e)}")
#             return None

#     async def store_access_token(self, user_id: int, token: str, expires_in: int) -> bool:
#         """Store access token with expiry"""
#         try:
#             key = f"{self.token_prefix}{user_id}"
#             await self.redis.setex(key, expires_in, token)
#             return True
#         except Exception as e:
#             logger.error(f"Error storing token: {str(e)}")
#             return False

#     async def check_retry_limit(self, user_id: int) -> Tuple[bool, int]:
#         """Check if user has exceeded retry limit"""
#         try:
#             key = f"{self.retry_prefix}{user_id}"
#             retries = await self.redis.get(key)
#             current_retries = int(retries) if retries else 0
#             remaining = self.max_retries - current_retries
            
#             return current_retries < self.max_retries, remaining
#         except Exception as e:
#             logger.error(f"Error checking retry limit: {str(e)}")
#             return False, 0

#     async def increment_retry_count(self, user_id: int):
#         """Increment retry count for user"""
#         try:
#             key = f"{self.retry_prefix}{user_id}"
#             await self.redis.incr(key)
#             await self.redis.expire(key, self.retry_expiry)
#         except Exception as e:
#             logger.error(f"Error incrementing retry count: {str(e)}")

#     async def reset_retry_count(self, user_id: int):
#         """Reset retry count for user"""
#         try:
#             key = f"{self.retry_prefix}{user_id}"
#             await self.redis.delete(key)
#         except Exception as e:
#             logger.error(f"Error resetting retry count: {str(e)}")

#     async def create_verification_request(self, user_id: int) -> Optional[str]:
#         """Create new verification request and return code"""
#         try:
#             can_retry, _ = await self.check_retry_limit(user_id)
#             if not can_retry:
#                 return None
                
#             code = datetime.now().strftime('%Y%m%d%H%M%S')
#             key = f"{self.verification_prefix}{user_id}"
#             await self.redis.setex(key, 3600, code)
#             await self.increment_retry_count(user_id)
            
#             return code
#         except Exception as e:
#             logger.error(f"Error creating verification: {str(e)}")
#             return None

#     async def verify_linkedin_comment(self, user_id: int, comment_code: str) -> bool:
#         """Verify LinkedIn comment contains verification code"""
#         try:
#             stored_code = await self.redis.get(f"{self.verification_prefix}{user_id}")
#             if not stored_code:
#                 return False
                
#             if comment_code == stored_code.decode('utf-8'):
#                 await self.reset_retry_count(user_id)
#                 return True
                
#             return False
#         except Exception as e:
#             logger.error(f"Error verifying comment: {str(e)}")
#             return False

#     async def authenticate_user(self, code: str) -> Optional[Dict]:
#         """Exchange OAuth code for access token"""
#         try:
#             async with aiohttp.ClientSession() as session:
#                 data = {
#                     'grant_type': 'authorization_code',
#                     'code': code,
#                     'client_id': self.config.client_id,
#                     'client_secret': self.config.client_secret,
#                     'redirect_uri': self.config.redirect_uri
#                 }
                
#                 async with session.post('https://www.linkedin.com/oauth/v2/accessToken', data=data) as resp:
#                     if resp.status != 200:
#                         logger.error(f"Authentication failed: {await resp.text()}")
#                         return None
#                     return await resp.json()
#         except Exception as e:
#             logger.error(f"Error authenticating: {str(e)}")
#             return None
