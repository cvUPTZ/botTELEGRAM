# linkedin_utils.py

import json
import redis
import asyncio
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from config import (
    REDIS_URL,
    LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET,
    LINKEDIN_REDIRECT_URI
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = redis.from_url(REDIS_URL)

class LinkedInError(Exception):
    """Custom exception for LinkedIn API errors"""
    pass

class TokenManager:
    def __init__(self):
        self.redis_client = redis_client
        
    async def get_valid_token(self) -> Optional[str]:
        """
        Get a valid LinkedIn access token, refreshing if necessary
        
        Returns:
            str: Valid access token or None if unable to get token
        """
        token_data = self.redis_client.get('linkedin_token')
        
        if token_data:
            token_data = json.loads(token_data)
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            
            # Check if token is still valid (with 5 minute buffer)
            if expires_at - timedelta(minutes=5) > datetime.utcnow():
                return token_data['access_token']
            
            # Token expired, try to refresh
            if 'refresh_token' in token_data:
                new_token = await self.refresh_token(token_data['refresh_token'])
                if new_token:
                    return new_token
        
        # No valid token available
        return None

    async def refresh_token(self, refresh_token: str) -> Optional[str]:
        """
        Refresh LinkedIn access token
        
        Args:
            refresh_token (str): The refresh token to use
            
        Returns:
            str: New access token or None if refresh failed
        """
        try:
            response = await asyncio.to_thread(
                requests.post,
                'https://www.linkedin.com/oauth/v2/accessToken',
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                    'client_id': LINKEDIN_CLIENT_ID,
                    'client_secret': LINKEDIN_CLIENT_SECRET
                },
                timeout=10
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            # Store new token data
            self.store_token_data(
                token_data['access_token'],
                token_data.get('refresh_token', refresh_token),
                token_data['expires_in']
            )
            
            return token_data['access_token']
            
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return None

    def store_token_data(self, access_token: str, refresh_token: str, expires_in: int):
        """Store token data in Redis"""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        token_data = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at.isoformat()
        }
        self.redis_client.set('linkedin_token', json.dumps(token_data))

token_manager = TokenManager()

async def verify_linkedin_comment(user_id: str) -> Tuple[bool, str]:
    """
    Verify if a user has commented on the LinkedIn post with their verification code
    
    Args:
        user_id (str): The user ID to verify
        
    Returns:
        Tuple[bool, str]: (success, message)
    """
    stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
    
    if not stored_code:
        return False, "Code de vérification non trouvé. Veuillez recommencer."
        
    stored_code = stored_code.decode('utf-8') if isinstance(stored_code, bytes) else stored_code
    
    try:
        # Get valid token
        access_token = await token_manager.get_valid_token()
        if not access_token:
            return False, "Erreur d'authentification LinkedIn. Veuillez réessayer plus tard."
        
        post_id = "7254038723820949505"
        comments_url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202304"
        }
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = await asyncio.to_thread(
                    requests.get,
                    comments_url,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 401:
                    # Token might be expired, force refresh
                    access_token = await token_manager.get_valid_token()
                    if not access_token:
                        return False, "Erreur d'authentification LinkedIn. Veuillez réessayer plus tard."
                    headers["Authorization"] = f"Bearer {access_token}"
                    retry_count += 1
                    continue
                        
                response.raise_for_status()
                
                comments = response.json().get('elements', [])
                logger.info(f"Retrieved {len(comments)} comments from LinkedIn post")
                
                # Cache successful response
                cache_key = f"linkedin_comments_cache:{post_id}"
                redis_client.setex(
                    cache_key,
                    timedelta(minutes=5),
                    json.dumps(comments)
                )
                
                for comment in comments:
                    comment_text = comment.get('message', {}).get('text', '').strip()
                    if stored_code in comment_text:
                        logger.info(f"Found matching verification code for user {user_id}")
                        
                        # Store verification success
                        verification_data = {
                            "verified_at": datetime.utcnow().isoformat(),
                            "comment_id": comment.get('id'),
                            "user_id": user_id
                        }
                        redis_client.set(
                            f"linkedin_verified:{user_id}",
                            json.dumps(verification_data)
                        )
                        
                        return True, "Vérification réussie!"
                
                return False, "Commentaire non trouvé. Assurez-vous d'avoir commenté avec le bon code."
                
            except requests.exceptions.RequestException as e:
                retry_count += 1
                if retry_count == max_retries:
                    return False, f"Erreur de connexion après {max_retries} tentatives. Veuillez réessayer plus tard."
                await asyncio.sleep(1)
                
    except Exception as e:
        logger.error(f"Error verifying LinkedIn comment: {str(e)}", exc_info=True)
        return False, "Une erreur est survenue. Veuillez réessayer plus tard."

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
