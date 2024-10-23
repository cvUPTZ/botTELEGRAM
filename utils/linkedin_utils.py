import time
import json
import redis
import aiohttp
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from config import (
    REDIS_URL,
    LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET,
    LINKEDIN_REDIRECT_URI,
    LINKEDIN_POST_ID,
    VERIFICATION_CODE_LENGTH,
    TOKEN_EXPIRY_BUFFER_MINUTES,
    API_TIMEOUT_SECONDS
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis key constants
REDIS_KEYS = {
    'TOKEN': 'linkedin_token',
    'AUTH_NEEDED': 'linkedin_auth_needed',
    'VERIFICATION_CODE': 'linkedin_verification_code:{}',
    'CODE_TIMESTAMP': 'linkedin_code_timestamp:{}',
    'EMAIL': 'linkedin_email:{}',
    'CV_TYPE': 'linkedin_cv_type:{}'
}

class LinkedInError(Exception):
    """Base exception for LinkedIn-related errors"""
    pass

class LinkedInAPIError(LinkedInError):
    """Specific exception for API errors"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)

class LinkedInAuthManager:
    """Handle LinkedIn authentication flow"""
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    def get_auth_url(self) -> str:
        """Generate LinkedIn authorization URL"""
        params = {
            'response_type': 'code',
            'client_id': LINKEDIN_CLIENT_ID,
            'redirect_uri': LINKEDIN_REDIRECT_URI,
            'scope': 'r_organization_social w_organization_social r_member_social'
        }
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.linkedin.com/oauth/v2/authorization?{query_string}"

    async def initialize_token(self, code: str) -> bool:
        """Initialize token with authorization code"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': LINKEDIN_CLIENT_ID,
                    'client_secret': LINKEDIN_CLIENT_SECRET,
                    'redirect_uri': LINKEDIN_REDIRECT_URI
                }
                
                async with session.post(
                    'https://www.linkedin.com/oauth/v2/accessToken',
                    data=data,
                    timeout=API_TIMEOUT_SECONDS
                ) as response:
                    if response.status != 200:
                        raise LinkedInAPIError(response.status, "Failed to initialize token")
                    
                    token_data = await response.json()
                    expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
                    
                    token_info = {
                        'access_token': token_data['access_token'],
                        'refresh_token': token_data.get('refresh_token'),
                        'expires_at': expires_at.isoformat()
                    }
                    
                    self.redis_client.set(REDIS_KEYS['TOKEN'], json.dumps(token_info))
                    self.redis_client.delete(REDIS_KEYS['AUTH_NEEDED'])
                    return True
                    
        except Exception as e:
            logger.error(f"Error initializing token: {str(e)}")
            return False

class TokenManager:
    """Handle LinkedIn token management"""
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    async def get_valid_token(self) -> Optional[str]:
        """Get a valid LinkedIn access token, refreshing if necessary"""
        try:
            token_data = self.redis_client.get(REDIS_KEYS['TOKEN'])
            
            if not token_data:
                logger.info("No token found, initiating authentication flow")
                return await self.handle_missing_token()
                
            token_data = json.loads(token_data)
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            
            if expires_at - timedelta(minutes=TOKEN_EXPIRY_BUFFER_MINUTES) > datetime.utcnow():
                logger.info("Using existing valid token")
                return token_data['access_token']
            
            if 'refresh_token' in token_data:
                logger.info("Token expired, attempting refresh")
                new_token = await self.refresh_token(token_data['refresh_token'])
                if new_token:
                    return new_token
                    
            return await self.handle_missing_token()
            
        except json.JSONDecodeError:
            logger.error("Invalid token data in Redis")
            self.redis_client.delete(REDIS_KEYS['TOKEN'])
            return await self.handle_missing_token()
            
        except Exception as e:
            logger.error(f"Error in get_valid_token: {str(e)}")
            return None

    async def handle_missing_token(self) -> Optional[str]:
        """Handle cases where no valid token exists"""
        self.redis_client.setex(REDIS_KEYS['AUTH_NEEDED'], 300, '1')
        return None

    async def refresh_token(self, refresh_token: str) -> Optional[str]:
        """Refresh LinkedIn access token"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                    'client_id': LINKEDIN_CLIENT_ID,
                    'client_secret': LINKEDIN_CLIENT_SECRET
                }
                
                async with session.post(
                    'https://www.linkedin.com/oauth/v2/accessToken',
                    data=data,
                    timeout=API_TIMEOUT_SECONDS
                ) as response:
                    if response.status != 200:
                        raise LinkedInAPIError(response.status, "Failed to refresh token")
                    
                    token_data = await response.json()
                    expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
                    
                    token_info = {
                        'access_token': token_data['access_token'],
                        'refresh_token': token_data.get('refresh_token', refresh_token),
                        'expires_at': expires_at.isoformat()
                    }
                    
                    self.redis_client.set(REDIS_KEYS['TOKEN'], json.dumps(token_info))
                    return token_data['access_token']
                    
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return None

class LinkedInVerificationManager:
    """Handle LinkedIn verification process"""
    def __init__(self, redis_client: redis.Redis, token_manager: TokenManager):
        self.redis_client = redis_client
        self.token_manager = token_manager

    async def verify_linkedin_comment(self, user_id: str) -> Tuple[bool, str]:
        """Verify if a user has commented on the LinkedIn post with their verification code"""
        try:
            stored_code = self.redis_client.get(REDIS_KEYS['VERIFICATION_CODE'].format(user_id))
            if not stored_code:
                return False, "Code de vérification non trouvé. Veuillez recommencer."

            stored_code = stored_code.decode('utf-8')
            
            access_token = await self.token_manager.get_valid_token()
            if not access_token:
                if self.redis_client.get(REDIS_KEYS['AUTH_NEEDED']):
                    return False, "Authentification LinkedIn requise. Un administrateur sera notifié."
                return False, "Erreur de connexion à LinkedIn. Veuillez réessayer plus tard."

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": "202304"
                }

                try:
                    async with session.get(
                        f"https://api.linkedin.com/v2/socialActions/{LINKEDIN_POST_ID}/comments",
                        headers=headers,
                        timeout=API_TIMEOUT_SECONDS
                    ) as response:
                        if response.status == 401:
                            self.redis_client.delete(REDIS_KEYS['TOKEN'])
                            return False, "Session LinkedIn expirée. Un administrateur sera notifié."

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
