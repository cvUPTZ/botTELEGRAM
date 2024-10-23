# linkedin_utils.py
import time
import json
import redis
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict
from config import (
    REDIS_URL,
    LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET,
    LINKEDIN_REDIRECT_URI
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = redis.from_url(REDIS_URL)

class LinkedInError(Exception):
    """Custom exception for LinkedIn API errors"""
    pass

class TokenManager:
    def __init__(self):
        self.redis_client = redis_client
        
    async def initialize_token(self, authorization_code: str) -> Optional[str]:
        """
        Initialize LinkedIn access token using authorization code
        """
        try:
            data = {
                'grant_type': 'authorization_code',
                'code': authorization_code,
                'client_id': LINKEDIN_CLIENT_ID,
                'client_secret': LINKEDIN_CLIENT_SECRET,
                'redirect_uri': LINKEDIN_REDIRECT_URI
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://www.linkedin.com/oauth/v2/accessToken',
                    data=data,
                    timeout=10
                ) as response:
                    if response.status != 200:
                        logger.error(f"Token initialization failed with status {response.status}")
                        return None
                        
                    token_data = await response.json()
                    
                    # Store new token data
                    self.store_token_data(
                        token_data['access_token'],
                        token_data.get('refresh_token', ''),
                        token_data['expires_in']
                    )
                    
                    logger.info("Successfully initialized token")
                    return token_data['access_token']
                    
        except Exception as e:
            logger.error(f"Error initializing token: {str(e)}")
            return None

    async def get_valid_token(self) -> Optional[str]:
        """
        Get a valid LinkedIn access token, refreshing if necessary
        """
        try:
            token_data = self.redis_client.get('linkedin_token')
            
            if not token_data:
                logger.error("No token found in Redis")
                raise LinkedInError("Token not initialized. Please authenticate with LinkedIn first.")
                
            token_data = json.loads(token_data)
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            
            # Check if token is expired (with 5 minute buffer)
            if expires_at - timedelta(minutes=5) > datetime.utcnow():
                logger.info("Using existing valid token")
                return token_data['access_token']
            
            # Token expired, try to refresh
            if 'refresh_token' in token_data:
                logger.info("Token expired, attempting refresh")
                new_token = await self.refresh_token(token_data['refresh_token'])
                if new_token:
                    return new_token
                    
            raise LinkedInError("Failed to get valid token. Please re-authenticate with LinkedIn.")
            
        except json.JSONDecodeError:
            logger.error("Invalid token data in Redis")
            self.redis_client.delete('linkedin_token')
            raise LinkedInError("Invalid token data. Please re-authenticate with LinkedIn.")
            
        except Exception as e:
            logger.error(f"Error in get_valid_token: {str(e)}")
            raise LinkedInError("Unexpected error occurred. Please try again later.")

    def get_auth_url(self) -> str:
        """
        Generate LinkedIn OAuth authorization URL
        """
        params = {
            'response_type': 'code',
            'client_id': LINKEDIN_CLIENT_ID,
            'redirect_uri': LINKEDIN_REDIRECT_URI,
            'scope': 'r_liteprofile w_member_social',
            'state': self._generate_state_param()
        }
        
        return f"https://www.linkedin.com/oauth/v2/authorization?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    def _generate_state_param(self) -> str:
        """Generate and store state parameter for OAuth security"""
        state = str(int(time.time()))
        self.redis_client.setex('linkedin_oauth_state', 300, state)  # 5 minute expiry
        return state

    def verify_state_param(self, state: str) -> bool:
        """Verify the state parameter returned by LinkedIn"""
        stored_state = self.redis_client.get('linkedin_oauth_state')
        return stored_state and stored_state.decode() == state

# Usage example:
async def authenticate_linkedin() -> Dict[str, str]:
    """
    Handle LinkedIn authentication flow
    Returns dict with status and either error message or success data
    """
    try:
        token_manager = TokenManager()
        auth_url = token_manager.get_auth_url()
        
        return {
            'status': 'redirect',
            'auth_url': auth_url
        }
        
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

async def handle_linkedin_callback(code: str, state: str) -> Dict[str, str]:
    """
    Handle LinkedIn OAuth callback
    """
    try:
        token_manager = TokenManager()
        
        if not token_manager.verify_state_param(state):
            raise LinkedInError("Invalid state parameter. Please try authenticating again.")
            
        access_token = await token_manager.initialize_token(code)
        if not access_token:
            raise LinkedInError("Failed to initialize token. Please try again.")
            
        return {
            'status': 'success',
            'message': 'Successfully authenticated with LinkedIn'
        }
        
    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }
def is_linkedin_verified(user_id: str) -> bool:
    """Check if a user has completed LinkedIn verification"""
    verified_data = redis_client.get(f"linkedin_verified:{user_id}")
    if not verified_data:
        return False
        
    try:
        data = json.loads(verified_data)
        verified_at = datetime.fromisoformat(data['verified_at'])
        return datetime.utcnow() - verified_at <= timedelta(days=30)
    except (json.JSONDecodeError, KeyError, ValueError):
        return False

def get_linkedin_profile(user_id: str) -> Optional[dict]:
    """Get the LinkedIn profile data for a verified user"""
    verified_data = redis_client.get(f"linkedin_verified:{user_id}")
    if verified_data:
        try:
            return json.loads(verified_data)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON data for user {user_id}")
    return None
