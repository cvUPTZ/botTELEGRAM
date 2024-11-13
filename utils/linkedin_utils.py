import logging
import aiohttp
import asyncio
import secrets
import string
import random
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from redis.asyncio import Redis
from redis.exceptions import RedisError

# Keep existing logging configuration
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
    
    def __init__(self, redis_client: Redis, config: LinkedInConfig):
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
    """LinkedIn API handler with improved error handling and rate limiting"""
    def __init__(self, access_token: str, rate_limit_window: int = 3600):
        self.access_token = access_token
        self.base_url = "https://api.linkedin.com/v2"
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json'
        }
        self.rate_limit_window = rate_limit_window
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def get_post_comments(self, post_id: str, max_retries: int = 3) -> list:
        """Fetch comments with retry logic and improved error handling"""
        for attempt in range(max_retries):
            try:
                session = await self.get_session()
                encoded_post_id = quote(post_id, safe='')
                async with session.get(
                    f"{self.base_url}/socialActions/{encoded_post_id}/comments"
                ) as response:
                    if response.status == 429:  # Rate limit exceeded
                        wait_time = int(response.headers.get('Retry-After', 60))
                        logger.warning(f"Rate limit exceeded, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    response.raise_for_status()
                    comments_data = await response.json()
                    
                    return [
                        {
                            'text': comment.get('message', {}).get('text', ''),
                            'actor': comment.get('actor', ''),
                            'created': comment.get('created', {}).get('time')
                        }
                        for comment in comments_data.get('elements', [])
                    ]
                    
            except aiohttp.ClientError as e:
                logger.error(f"API request failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
        return []

class LinkedInVerificationManager:
    """Verification manager with improved security and validation"""
    
    def __init__(
        self,
        redis_client: Redis,
        linkedin_api: LinkedInAPI,
        verification_ttl: int = 3600,
        max_verification_attempts: int = 3
    ):
        self.redis = redis_client
        self.linkedin_api = linkedin_api
        self.verification_ttl = verification_ttl
        self.max_attempts = max_verification_attempts
        self.prefix = "linkedin_verification:"

    async def _ensure_redis_connection(self) -> None:
        """Ensure Redis connection is available."""
        if self.redis is None:
            raise LinkedInError("Redis client not initialized", LinkedInErrorCode.REDIS_ERROR)
        try:
            await self.redis.ping()
        except (RedisError, AttributeError) as e:
            logger.error(f"Redis connection error: {str(e)}")
            raise LinkedInError("Redis connection failed", LinkedInErrorCode.REDIS_ERROR)

    async def generate_verification_code(self, user_id: int) -> str:
        """Generate unique verification code with collision checking"""
        try:
            await self._ensure_redis_connection()
            while True:
                code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
                key = f"{self.prefix}code:{code}"
                exists = await self.redis.exists(key)
                if not exists:
                    await self.redis.setex(
                        key,
                        self.verification_ttl,
                        str(user_id)
                    )
                    return code
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error generating verification code: {str(e)}")
            raise LinkedInError("Failed to generate verification code", LinkedInErrorCode.REDIS_ERROR)

    async def verify_linkedin_comment(
        self,
        user_id: int,
        verification_code: str,
        post_id: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Enhanced verification with time window and attempt tracking"""
        try:
            await self._ensure_redis_connection()
            
            # Check verification attempts
            attempts_key = f"{self.prefix}attempts:{user_id}"
            attempts = await self.redis.incr(attempts_key)
            if attempts == 1:
                await self.redis.expire(attempts_key, self.verification_ttl)
            
            if attempts > self.max_attempts:
                return False, "❌ Trop de tentatives. Veuillez réessayer plus tard.", None

            # Get stored verification data
            code_key = f"{self.prefix}code:{verification_code}"
            stored_user_id = await self.redis.get(code_key)
            
            if not stored_user_id or int(stored_user_id) != user_id:
                return False, "❌ Code de vérification invalide ou expiré.", None

            # Fetch and verify comments
            comments = await self.linkedin_api.get_post_comments(post_id)
            
            for comment in comments:
                if verification_code in comment['text']:
                    # Store verification success
                    await self.store_verification_success(user_id, comment)
                    return True, "✅ Vérification réussie!", comment

            return False, "❌ Code non trouvé dans les commentaires récents. Veuillez réessayer.", None

        except LinkedInError as e:
            logger.error(f"LinkedIn error during verification for user {user_id}: {str(e)}")
            return False, f"❌ Erreur LinkedIn: {e.message}", None
        except Exception as e:
            logger.error(f"Verification error for user {user_id}: {str(e)}")
            return False, "❌ Une erreur s'est produite lors de la vérification.", None

    async def store_verification_success(self, user_id: int, comment_data: dict) -> None:
        """Store successful verification data"""
        try:
            await self._ensure_redis_connection()
            success_key = f"{self.prefix}success:{user_id}"
            await self.redis.hmset(success_key, {
                'timestamp': datetime.utcnow().isoformat(),
                'comment_actor': comment_data['actor'],
                'comment_time': comment_data['created']
            })
            await self.redis.expire(success_key, 86400)  # Store for 24 hours
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error storing verification success: {str(e)}")
            raise LinkedInError("Failed to store verification success", LinkedInErrorCode.REDIS_ERROR)

    async def cleanup_verification_data(self, user_id: int, verification_code: str) -> None:
        """Clean up all verification-related data"""
        try:
            await self._ensure_redis_connection()
            keys = [
                f"{self.prefix}code:{verification_code}",
                f"{self.prefix}attempts:{user_id}"
            ]
            await self.redis.delete(*keys)
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error cleaning up verification data: {str(e)}")
            raise LinkedInError("Failed to cleanup verification data", LinkedInErrorCode.REDIS_ERROR)





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
