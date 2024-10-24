import logging
import aiohttp
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timedelta
from redis.asyncio import Redis
from redis.exceptions import RedisError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LinkedInError(Exception):
    """Custom exception for LinkedIn API errors"""
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

class LinkedInErrorCode:
    """Error codes for LinkedIn API"""
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_REQUEST = "INVALID_REQUEST"
    API_ERROR = "API_ERROR"

class LinkedInConfig:
    """Configuration class for LinkedIn integration"""
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        post_url: str,
        access_token: str,
        scope: str,
        company_page_id: int,
        post_id: str
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.post_url = post_url
        self.access_token = access_token
        self.scope = scope
        self.company_page_id = company_page_id
        self.post_id = post_id

class LinkedInTokenManager:
    """Manage LinkedIn access tokens"""
    
    def __init__(self, redis_client: Redis, config: LinkedInConfig):
        self.redis = redis_client
        self.config = config
        self.token_key_prefix = "linkedin_token:"
        self.token_expiry_prefix = "linkedin_token_expiry:"
    
    async def get_token(self, user_id: int) -> Optional[str]:
        """Get valid access token for user"""
        token = self.redis.get(f"{self.token_key_prefix}{user_id}")
        if not token:
            return None
            
        expiry = self.redis.get(f"{self.token_expiry_prefix}{user_id}")
        if not expiry or float(expiry) < datetime.utcnow().timestamp():
            return None
            
        return token.decode('utf-8')

    async def store_token(
        self,
        user_id: int,
        access_token: str,
        expires_in: int
    ) -> None:
        """Store access token with expiry"""
        expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        pipeline = self.redis.pipeline()
        pipeline.setex(
            f"{self.token_key_prefix}{user_id}",
            expires_in,
            access_token
        )
        pipeline.setex(
            f"{self.token_expiry_prefix}{user_id}",
            expires_in,
            expiry.timestamp()
        )
        pipeline.execute()

    async def refresh_token(self, user_id: int) -> Optional[str]:
        """Refresh expired access token"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'refresh_token',
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret,
                    'refresh_token': await self.get_refresh_token(user_id)
                }
                
                async with session.post(
                    'https://www.linkedin.com/oauth/v2/accessToken',
                    data=data
                ) as response:
                    if response.status != 200:
                        raise LinkedInError(
                            "Failed to refresh token",
                            LinkedInErrorCode.TOKEN_EXPIRED
                        )
                        
                    result = await response.json()
                    await self.store_token(
                        user_id,
                        result['access_token'],
                        result['expires_in']
                    )
                    return result['access_token']
                    
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return None

    async def get_refresh_token(self, user_id: int) -> Optional[str]:
        """Get refresh token for user"""
        token = self.redis.get(f"linkedin_refresh_token:{user_id}")
        return token.decode('utf-8') if token else None

class LinkedInVerificationManager:
    """Manage LinkedIn comment verification process with improved async handling"""
    
    def __init__(
        self,
        redis_client: Redis,
        token_manager: 'LinkedInTokenManager',
        config: 'LinkedInConfig',
        verification_ttl: int = 3600
    ):
        self.redis = redis_client
        self.token_manager = token_manager
        self.config = config
        self.verification_ttl = verification_ttl
        
    async def verify_linkedin_comment(
        self,
        user_id: int,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> Tuple[bool, str]:
        """
        Verify user's LinkedIn comment with improved error handling and retries
        
        Args:
            user_id: The user's ID
            max_retries: Maximum number of API retry attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Get stored verification data
            verification_code = await self._get_stored_code(user_id)
            if not verification_code:
                return False, "❌ Code de vérification expiré ou introuvable."
            
            # Get access token with fallback
            access_token = await self._get_valid_access_token(user_id)
            if not access_token:
                return False, "❌ Erreur d'authentification LinkedIn."
            
            # Check for comment with retries
            for attempt in range(max_retries):
                try:
                    found = await self._check_linkedin_comment(
                        access_token,
                        verification_code
                    )
                    
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
                    elif attempt == max_retries - 1:
                        raise
                        
        except LinkedInError as e:
            logger.error(f"LinkedIn error during verification: {str(e)}", exc_info=True)
            return False, self._get_user_friendly_error_message(e)
            
        except RedisError as e:
            logger.error(f"Redis error during verification: {str(e)}", exc_info=True)
            return False, "❌ Erreur temporaire de stockage. Veuillez réessayer."
            
        except Exception as e:
            logger.error(f"Unexpected error during verification: {str(e)}", exc_info=True)
            return False, "❌ Une erreur inattendue s'est produite. Veuillez réessayer."

    async def _check_linkedin_comment(
        self,
        access_token: str,
        verification_code: str,
        timeout: float = 10.0
    ) -> bool:
        """Check if verification code exists in post comments with timeout"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'X-Restli-Protocol-Version': '2.0.0',
                    'Content-Type': 'application/json'
                }
                
                url = (
                    f"https://api.linkedin.com/v2/socialActions/"
                    f"{self.config.company_page_id}_"
                    f"{self.config.post_id}/comments"
                )
                
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 429:
                        raise LinkedInError(
                            "Rate limit exceeded",
                            LinkedInErrorCode.RATE_LIMIT_EXCEEDED
                        )
                    elif response.status == 401:
                        raise LinkedInError(
                            "Invalid token",
                            LinkedInErrorCode.INVALID_TOKEN
                        )
                    elif response.status != 200:
                        raise LinkedInError(
                            f"API error (status {response.status})",
                            LinkedInErrorCode.API_ERROR
                        )
                        
                    data = await response.json()
                    return self._find_verification_code_in_comments(
                        data.get('elements', []),
                        verification_code
                    )
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error checking comment: {str(e)}")
            raise LinkedInError(
                "Network error when checking comment",
                LinkedInErrorCode.API_ERROR
            )

    async def _get_stored_code(self, user_id: int) -> Optional[str]:
        """Get stored verification code with error handling"""
        try:
            code = await self.redis.get(f"linkedin_verification_code:{user_id}")
            return code.decode('utf-8') if code else None
        except RedisError as e:
            logger.error(f"Redis error getting stored code: {str(e)}")
            return None

    async def _cleanup_verification_data(self, user_id: int) -> None:
        """Clean up verification data from Redis with error handling"""
        try:
            await self.redis.delete(f"linkedin_verification_code:{user_id}")
        except RedisError as e:
            logger.error(f"Redis error cleaning up verification data: {str(e)}")

    async def _get_valid_access_token(self, user_id: int) -> Optional[str]:
        """Get valid access token with fallback to config token"""
        try:
            token = await self.token_manager.get_token(user_id)
            return token if token else self.config.access_token
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            return self.config.access_token

    @staticmethod
    def _find_verification_code_in_comments(
        comments: List[Dict[str, Any]],
        verification_code: str
    ) -> bool:
        """Safely search for verification code in comments"""
        try:
            return any(
                verification_code in comment.get('message', {}).get('text', '')
                for comment in comments
            )
        except Exception as e:
            logger.error(f"Error parsing comments: {str(e)}")
            return False

    @staticmethod
    def _get_user_friendly_error_message(error: LinkedInError) -> str:
        """Convert LinkedIn errors to user-friendly messages"""
        error_messages = {
            LinkedInErrorCode.TOKEN_EXPIRED: "❌ Session LinkedIn expirée. Veuillez réessayer.",
            LinkedInErrorCode.INVALID_TOKEN: "❌ Erreur d'authentification LinkedIn.",
            LinkedInErrorCode.RATE_LIMIT_EXCEEDED: "❌ Trop de requêtes. Veuillez patienter quelques minutes.",
            LinkedInErrorCode.API_ERROR: "❌ Erreur de communication avec LinkedIn. Veuillez réessayer."
        }
        return error_messages.get(error.code, "❌ Une erreur s'est produite. Veuillez réessayer.")
