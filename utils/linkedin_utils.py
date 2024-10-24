import time
import json
import redis
import aiohttp
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LinkedInErrorCode(Enum):
    """Enum for LinkedIn API error codes"""
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"

@dataclass
class LinkedInConfig:
    """Configuration class for LinkedIn API"""
    client_id: str
    client_secret: str
    redirect_uri: str
    post_id: str
    verification_code_length: int
    token_expiry_buffer_minutes: int
    api_timeout_seconds: int

class LinkedInError(Exception):
    """Base exception for LinkedIn-related errors"""
    def __init__(self, message: str, error_code: LinkedInErrorCode = LinkedInErrorCode.UNKNOWN):
        self.error_code = error_code
        super().__init__(message)

class LinkedInAPIError(LinkedInError):
    """Specific exception for API errors"""
    def __init__(self, status_code: int, message: str, error_code: LinkedInErrorCode):
        self.status_code = status_code
        super().__init__(message, error_code)

class RedisKeys:
    """Redis key constants"""
    TOKEN = 'linkedin_token'
    AUTH_NEEDED = 'linkedin_auth_needed'
    VERIFICATION_CODE = 'linkedin_verification_code:{}'
    CODE_TIMESTAMP = 'linkedin_code_timestamp:{}'
    EMAIL = 'linkedin_email:{}'
    CV_TYPE = 'linkedin_cv_type:{}'

class LinkedInAuthManager:
    """Handle LinkedIn authentication flow with improved error handling"""
    def __init__(self, redis_client: redis.Redis, config: LinkedInConfig):
        self.redis_client = redis_client
        self.config = config

    def get_auth_url(self) -> str:
        """Generate LinkedIn authorization URL"""
        params = {
            'response_type': 'code',
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'scope': 'r_organization_social w_organization_social r_member_social'
        }
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.linkedin.com/oauth/v2/authorization?{query_string}"

    async def initialize_token(self, code: str) -> Tuple[bool, str]:
        """Initialize token with authorization code"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret,
                    'redirect_uri': self.config.redirect_uri
                }
                
                async with session.post(
                    'https://www.linkedin.com/oauth/v2/accessToken',
                    data=data,
                    timeout=self.config.api_timeout_seconds
                ) as response:
                    if response.status == 401:
                        raise LinkedInAPIError(
                            401,
                            "Invalid authorization code",
                            LinkedInErrorCode.AUTH_ERROR
                        )
                    
                    if response.status != 200:
                        raise LinkedInAPIError(
                            response.status,
                            f"LinkedIn API error: {response.status}",
                            LinkedInErrorCode.SERVER_ERROR
                        )
                    
                    token_data = await response.json()
                    expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
                    
                    token_info = {
                        'access_token': token_data['access_token'],
                        'refresh_token': token_data.get('refresh_token'),
                        'expires_at': expires_at.isoformat()
                    }
                    
                    self.redis_client.set(RedisKeys.TOKEN, json.dumps(token_info))
                    self.redis_client.delete(RedisKeys.AUTH_NEEDED)
                    
                    logger.info("LinkedIn token initialized successfully")
                    return True, "Authentication successful"
                    
        except LinkedInAPIError as e:
            logger.error(f"LinkedIn API error: {str(e)}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error initializing token: {str(e)}")
            return False, "Technical error during authentication"

class LinkedInTokenManager:
    """Handle LinkedIn token management with improved error handling"""
    def __init__(self, redis_client: redis.Redis, config: LinkedInConfig):
        self.redis_client = redis_client
        self.config = config

    async def get_valid_token(self) -> Optional[str]:
        """Get a valid LinkedIn access token, refreshing if necessary"""
        try:
            token_data = self.redis_client.get(RedisKeys.TOKEN)
            
            if not token_data:
                logger.info("No token found, setting auth needed flag")
                self.redis_client.setex(RedisKeys.AUTH_NEEDED, 3600, '1')
                return None
                
            token_info = json.loads(token_data)
            expires_at = datetime.fromisoformat(token_info['expires_at'])
            
            if expires_at - timedelta(minutes=self.config.token_expiry_buffer_minutes) > datetime.utcnow():
                return token_info['access_token']
            
            if 'refresh_token' in token_info:
                logger.info("Token expired, attempting refresh")
                return await self.refresh_token(token_info['refresh_token'])
            
            logger.info("Token refresh failed, setting auth needed flag")
            self.redis_client.setex(RedisKeys.AUTH_NEEDED, 3600, '1')
            return None
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid token data in Redis: {str(e)}")
            self.cleanup_token_data()
            return None
        except Exception as e:
            logger.error(f"Error in get_valid_token: {str(e)}")
            return None

    async def refresh_token(self, refresh_token: str) -> Optional[str]:
        """Refresh LinkedIn access token"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret
                }
                
                async with session.post(
                    'https://www.linkedin.com/oauth/v2/accessToken',
                    data=data,
                    timeout=self.config.api_timeout_seconds
                ) as response:
                    if response.status != 200:
                        raise LinkedInAPIError(
                            response.status,
                            "Token refresh failed",
                            LinkedInErrorCode.AUTH_ERROR
                        )
                    
                    token_data = await response.json()
                    expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
                    
                    token_info = {
                        'access_token': token_data['access_token'],
                        'refresh_token': token_data.get('refresh_token', refresh_token),
                        'expires_at': expires_at.isoformat()
                    }
                    
                    self.redis_client.set(RedisKeys.TOKEN, json.dumps(token_info))
                    self.redis_client.delete(RedisKeys.AUTH_NEEDED)
                    return token_data['access_token']
                    
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            self.cleanup_token_data()
            return None

    def cleanup_token_data(self):
        """Clean up token data in Redis"""
        self.redis_client.delete(RedisKeys.TOKEN)
        self.redis_client.setex(RedisKeys.AUTH_NEEDED, 3600, '1')

class LinkedInVerificationManager:
    """Handle LinkedIn verification process"""
    def __init__(self, redis_client: redis.Redis, token_manager: LinkedInTokenManager, config: LinkedInConfig):
        self.redis_client = redis_client
        self.token_manager = token_manager
        self.config = config

    async def verify_linkedin_comment(self, user_id: str) -> Tuple[bool, str]:
        """Verify if a user has commented on the LinkedIn post with their verification code"""
        try:
            stored_code = self.redis_client.get(RedisKeys.VERIFICATION_CODE.format(user_id))
            if not stored_code:
                return False, "Verification code not found. Please try again."

            stored_code = stored_code.decode('utf-8')
            
            access_token = await self.token_manager.get_valid_token()
            if not access_token:
                if self.redis_client.get(RedisKeys.AUTH_NEEDED):
                    return False, "LinkedIn authentication required. An administrator will be notified."
                return False, "LinkedIn connection error. Please try again later."

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": "202304"
                }

                try:
                    async with session.get(
                        f"https://api.linkedin.com/v2/socialActions/{self.config.post_id}/comments",
                        headers=headers,
                        timeout=self.config.api_timeout_seconds
                    ) as response:
                        if response.status == 401:
                            self.redis_client.delete(RedisKeys.TOKEN)
                            return False, "LinkedIn session expired. An administrator will be notified."

                        if response.status != 200:
                            raise LinkedInAPIError(
                                response.status,
                                "LinkedIn API error",
                                LinkedInErrorCode.SERVER_ERROR
                            )

                        data = await response.json()
                        return await self.process_comments(data, stored_code, user_id)

                except asyncio.TimeoutError:
                    logger.error("LinkedIn API timeout")
                    return False, "Request timed out. Please try again later."

                except aiohttp.ClientError as e:
                    logger.error(f"Network error: {str(e)}")
                    return False, "Network connection error. Please try again later."

        except Exception as e:
            logger.error(f"Error verifying LinkedIn comment: {str(e)}")
            return False, "Technical error. Please try again later."

    async def process_comments(self, data: Dict[str, Any], stored_code: str, user_id: str) -> Tuple[bool, str]:
        """Process LinkedIn comments to find verification code"""
        comments = data.get('elements', [])
        if not comments:
            return False, "No comments found. Please make sure you commented with the provided code."

        code_timestamp = self.redis_client.get(RedisKeys.CODE_TIMESTAMP.format(user_id))
        if not code_timestamp:
            return False, "Session expired. Please start over."

        code_timestamp = float(code_timestamp.decode('utf-8'))

        for comment in comments:
            comment_text = comment.get('message', {}).get('text', '').strip()
            comment_time = int(comment.get('created', {}).get('time', 0)) / 1000

            if stored_code == comment_text and comment_time > code_timestamp:
                logger.info(f"Valid comment found for user {user_id}")
                return True, "Verification successful!"

        return False, "Verification code not found in comments. Please make sure you copied the code exactly."
