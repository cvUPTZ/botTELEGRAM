import logging
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

import redis
from redis import Redis

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
    """Manage LinkedIn comment verification process"""
    
    def __init__(
        self,
        redis_client: Redis,
        token_manager: LinkedInTokenManager,
        config: LinkedInConfig
    ):
        self.redis = redis_client
        self.token_manager = token_manager
        self.config = config
        self.verification_ttl = 3600  # 1 hour
        
    async def verify_linkedin_comment(
        self,
        user_id: int
    ) -> Tuple[bool, str]:
        """Verify user's LinkedIn comment"""
        try:
            # Get stored verification data
            verification_code = self.redis.get(f"linkedin_verification_code:{user_id}")
            if not verification_code:
                return False, "❌ Code de vérification expiré ou introuvable."
            
            verification_code = verification_code.decode('utf-8')
            
            # Get access token
            access_token = await self.token_manager.get_token(user_id)
            if not access_token:
                access_token = self.config.access_token
            
            # Check for comment
            found = await self._check_linkedin_comment(
                access_token,
                verification_code
            )
            
            if found:
                return True, "✅ Commentaire vérifié avec succès!"
            else:
                return False, (
                    "❌ Commentaire non trouvé. Assurez-vous d'avoir:\n"
                    "1. Commenté sur la bonne publication\n"
                    "2. Utilisé le bon code de vérification\n"
                    "3. Attendu quelques secondes après avoir commenté"
                )
                
        except LinkedInError as e:
            logger.error(f"LinkedIn error during verification: {str(e)}")
            return False, f"❌ Erreur LinkedIn: {e.message}"
            
        except Exception as e:
            logger.error(f"Error during verification: {str(e)}")
            return False, "❌ Une erreur s'est produite lors de la vérification."

    async def _check_linkedin_comment(
        self,
        access_token: str,
        verification_code: str
    ) -> bool:
        """Check if verification code exists in post comments"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'X-Restli-Protocol-Version': '2.0.0',
                    'Content-Type': 'application/json'
                }
                
                # Get post comments
                url = (
                    f"https://api.linkedin.com/v2/socialActions/"
                    f"{self.config.company_page_id}_"
                    f"{self.config.post_id}/comments"
                )
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        raise LinkedInError(
                            "Failed to fetch comments",
                            LinkedInErrorCode.API_ERROR
                        )
                        
                    data = await response.json()
                    
                    # Check comments for verification code
                    for comment in data.get('elements', []):
                        if verification_code in comment.get('message', {}).get('text', ''):
                            return True
                            
                    return False
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error checking comment: {str(e)}")
            raise LinkedInError(
                "Network error when checking comment",
                LinkedInErrorCode.API_ERROR
            )
            
        except Exception as e:
            logger.error(f"Error checking LinkedIn comment: {str(e)}")
            raise LinkedInError(
                "Error checking comment",
                LinkedInErrorCode.API_ERROR
            )

    async def store_verification_data(
        self,
        user_id: int,
        verification_code: str
    ) -> None:
        """Store verification data in Redis"""
        self.redis.setex(
            f"linkedin_verification_code:{user_id}",
            self.verification_ttl,
            verification_code
        )

    async def get_stored_code(self, user_id: int) -> Optional[str]:
        """Get stored verification code"""
        code = self.redis.get(f"linkedin_verification_code:{user_id}")
        return code.decode('utf-8') if code else None

    async def cleanup_verification_data(self, user_id: int) -> None:
        """Clean up verification data from Redis"""
        self.redis.delete(f"linkedin_verification_code:{user_id}")
