import logging
import aiohttp
import asyncio
import secrets
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from redis.asyncio import Redis
from redis.exceptions import RedisError

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

class LinkedInVerificationManager:
    """Manage LinkedIn comment verification process."""
    
    def __init__(self, 
                 redis_client: Optional[Redis], 
                 token_manager: LinkedInTokenManager, 
                 config: LinkedInConfig, 
                 verification_ttl: int = 3600):
        self.redis = redis_client
        self.token_manager = token_manager
        self.config = config
        self.verification_ttl = verification_ttl
        self.verification_code_prefix = "linkedin_verification_code:"

    async def _ensure_redis_connection(self) -> None:
        """Ensure Redis connection is available and properly initialized."""
        if not hasattr(self, 'redis') or self.redis is None or isinstance(self.redis, bool):
            try:
                self.redis = await aioredis.create_redis_pool(
                    "redis://:AYarAAIjcDFkOTIwODA5NTAwM2Y0MDY0YWY5OWZhMTk1Yjg5Y2Y0ZHAxMA@devoted-filly-34475.upstash.io:6379"
                )
            except RedisError as e:
                logger.error(f"Failed to initialize Redis connection: {str(e)}")
                raise LinkedInError("Redis client initialization failed", LinkedInErrorCode.REDIS_ERROR)
        
        try:
            is_connected = await self.redis.ping()
            if not is_connected:
                raise LinkedInError("Redis ping failed", LinkedInErrorCode.REDIS_ERROR)
        except (RedisError, AttributeError) as e:
            logger.error(f"Redis connection error: {str(e)}")
            raise LinkedInError("Redis connection failed", LinkedInErrorCode.REDIS_ERROR)


    async def generate_verification_code(self, user_id: int, length: int = 6) -> str:
        """Generate and store a new verification code for the user."""
        try:
            await self._ensure_redis_connection()
            
            # Generate a random verification code
            verification_code = secrets.token_hex(length)[:length].upper()
            
            # Store the code with expiration
            await self.redis.setex(
                f"{self.verification_code_prefix}{user_id}",
                self.verification_ttl,
                verification_code
            )
            
            return verification_code
            
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error generating verification code: {str(e)}")
            raise LinkedInError("Failed to generate verification code", LinkedInErrorCode.REDIS_ERROR)

    async def _get_valid_access_token(self, user_id: int) -> str:
        """Get a valid access token for the user."""
        try:
            access_token = await self.token_manager.get_token(user_id)
            if not access_token:
                logger.debug(f"No valid access token for user {user_id}, attempting to refresh...")
                access_token = await self.token_manager.refresh_token(user_id)
                if not access_token:
                    raise LinkedInError("Failed to obtain valid access token", LinkedInErrorCode.TOKEN_EXPIRED)
            return access_token
        except LinkedInError:
            raise
        except Exception as e:
            logger.error(f"Error getting valid access token: {str(e)}")
            raise LinkedInError("Failed to obtain access token", LinkedInErrorCode.API_ERROR)

    async def _check_linkedin_comment(self, access_token: str, verification_code: str, timeout: float = 10.0) -> bool:
        """Check if verification code exists in post comments."""
        url = f"https://api.linkedin.com/v2/socialActions/{self.config.post_id}/comments"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 429:
                        raise LinkedInError("Rate limit exceeded", LinkedInErrorCode.RATE_LIMIT_EXCEEDED)
                    elif response.status == 401:
                        raise LinkedInError("Invalid or expired token", LinkedInErrorCode.TOKEN_EXPIRED)
                    elif response.status != 200:
                        error_text = await response.text()
                        logger.error(f"LinkedIn API error: {error_text}")
                        raise LinkedInError("Failed to fetch comments", LinkedInErrorCode.API_ERROR)
                    
                    data = await response.json()
                    comments = data.get('elements', [])
                    
                    for comment in comments:
                        if 'specificContent' in comment and 'com.linkedin.ugc.ShareContent' in comment['specificContent']:
                            text = comment['specificContent']['com.linkedin.ugc.ShareContent']['text']
                            if verification_code in text:
                                return True
                    
                    return False
    
        except asyncio.TimeoutError:
            logger.error("Request to LinkedIn API timed out")
            raise LinkedInError("Request timed out", LinkedInErrorCode.API_ERROR)
        except LinkedInError:
            raise
        except Exception as e:
            logger.error(f"Error checking LinkedIn comment: {str(e)}")
            raise LinkedInError("Failed to check comment", LinkedInErrorCode.API_ERROR)

    async def verify_linkedin_comment(self, user_id: int, max_retries: int = 3, retry_delay: float = 1.0) -> Tuple[bool, str]:
        """Verify user's LinkedIn comment with improved error handling and retries."""
        try:
            # Ensure Redis connection is properly initialized
            await self._ensure_redis_connection()
            
            verification_code = await self._get_stored_code(user_id)
            if not verification_code:
                return False, "❌ Code de vérification expiré ou introuvable."
            
            access_token = await self._get_valid_access_token(user_id)
            
            for attempt in range(max_retries):
                try:
                    found = await self._check_linkedin_comment(access_token, verification_code)
                    if found:
                        await self._cleanup_verification_data(user_id)
                        return True, "✅ Commentaire vérifié avec succès!"
                    
                    if attempt == max_retries - 1:
                        return False, (
                            "❌ Commentaire non trouvé. Assurez-vous d'avoir:\n"
                            "1. Commenté sur la bonne publication\n"
                            "2. Utilisé le bon code de vérification\n"
                            "3. Attendu quelques secondes après avoir commenté"
                        )
                    
                    await asyncio.sleep(retry_delay)
                    
                except LinkedInError as e:
                    if e.code in [LinkedInErrorCode.TOKEN_EXPIRED, LinkedInErrorCode.INVALID_TOKEN]:
                        access_token = await self.token_manager.refresh_token(user_id)
                        if not access_token:
                            return False, "❌ Erreur de rafraîchissement du token LinkedIn."
                        continue
                    elif attempt == max_retries - 1:
                        raise
                        
        except LinkedInError as e:
            logger.error(f"LinkedIn error during verification: {str(e)}", exc_info=True)
            return False, self._get_user_friendly_error_message(e)
        except Exception as e:
            logger.error(f"Unexpected error during verification: {str(e)}", exc_info=True)
            return False, "❌ Une erreur inattendue s'est produite. Veuillez réessayer."

    async def _get_stored_code(self, user_id: int) -> Optional[str]:
        """Get stored verification code with error handling."""
        try:
            await self._ensure_redis_connection()
            code = await self.redis.get(f"{self.verification_code_prefix}{user_id}")
            return code.decode('utf-8') if code else None
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error getting stored code: {str(e)}")
            return None

    async def _cleanup_verification_data(self, user_id: int) -> None:
        """Cleanup verification data from Redis."""
        try:
            await self._ensure_redis_connection()
            await self.redis.delete(f"{self.verification_code_prefix}{user_id}")
        except (LinkedInError, RedisError) as e:
            logger.error(f"Error during cleanup: {str(e)}")

    def _get_user_friendly_error_message(self, error: LinkedInError) -> str:
        """Map LinkedIn errors to user-friendly messages."""
        error_messages = {
            LinkedInErrorCode.TOKEN_EXPIRED: "❌ Votre session a expiré. Veuillez vous reconnecter.",
            LinkedInErrorCode.INVALID_TOKEN: "❌ Session invalide. Veuillez vous reconnecter.",
            LinkedInErrorCode.RATE_LIMIT_EXCEEDED: "❌ Trop de requêtes. Veuillez patienter quelques minutes.",
            LinkedInErrorCode.INVALID_REQUEST: "❌ Requête invalide. Veuillez réessayer.",
            LinkedInErrorCode.API_ERROR: "❌ Erreur de communication avec LinkedIn.",
            LinkedInErrorCode.REDIS_ERROR: "❌ Erreur de stockage temporaire."
        }
        return error_messages.get(error.code, "❌ Une erreur inattendue s'est produite.")




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
