import logging
import aiohttp
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timedelta
from redis import Redis  # Changed from redis.asyncio
from redis.exceptions import RedisError

# ... (previous imports and logging setup remain the same)

class LinkedInVerificationManager:
    """Manage LinkedIn comment verification process"""
    
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
        """
        try:
            # Get stored verification data - no await needed
            verification_code = self._get_stored_code(user_id)
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
                        self._cleanup_verification_data(user_id)  # No await needed
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

    def _get_stored_code(self, user_id: int) -> Optional[str]:
        """Get stored verification code with error handling - synchronous version"""
        try:
            code = self.redis.get(f"linkedin_verification_code:{user_id}")
            if code is not None:
                return code.decode('utf-8')
            return None
        except RedisError as e:
            logger.error(f"Redis error getting stored code: {str(e)}")
            return None

    def _cleanup_verification_data(self, user_id: int) -> None:
        """Clean up verification data from Redis with error handling - synchronous version"""
        try:
            self.redis.delete(f"linkedin_verification_code:{user_id}")
        except RedisError as e:
            logger.error(f"Redis error cleaning up verification data: {str(e)}")

    async def _get_valid_access_token(self, user_id: int) -> Optional[str]:
        """Get valid access token with fallback to config token"""
        try:
            # Note: get_token is still async as it might involve network operations
            token = await self.token_manager.get_token(user_id)
            return token if token else self.config.access_token
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            return self.config.access_token

class LinkedInTokenManager:
    """Manage LinkedIn access tokens"""
    
    def __init__(self, redis_client: Redis, config: LinkedInConfig):
        self.redis = redis_client
        self.config = config
        self.token_key_prefix = "linkedin_token:"
        self.token_expiry_prefix = "linkedin_token_expiry:"
    
    async def get_token(self, user_id: int) -> Optional[str]:
        """Get valid access token for user"""
        # No await needed for Redis operations
        token = self.redis.get(f"{self.token_key_prefix}{user_id}")
        if not token:
            return None
    
        expiry = self.redis.get(f"{self.token_expiry_prefix}{user_id}")
        if not expiry or float(expiry.decode('utf-8')) < datetime.utcnow().timestamp():
            return None
    
        return token.decode('utf-8')

    def store_token(
        self,
        user_id: int,
        access_token: str,
        expires_in: int
    ) -> None:
        """Store access token with expiry - synchronous version"""
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

    def get_refresh_token(self, user_id: int) -> Optional[str]:
        """Get refresh token for user - synchronous version"""
        token = self.redis.get(f"linkedin_refresh_token:{user_id}")
        return token.decode('utf-8') if token else None

    async def refresh_token(self, user_id: int) -> Optional[str]:
        """Refresh expired access token"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'refresh_token',
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret,
                    'refresh_token': self.get_refresh_token(user_id)  # No await needed
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
                    self.store_token(  # No await needed
                        user_id,
                        result['access_token'],
                        result['expires_in']
                    )
                    return result['access_token']
                    
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return None
