# linkedin_utils.py
import time
import json
import redis
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

    async def get_valid_token(self) -> Optional[str]:
        """
        Get a valid LinkedIn access token, refreshing if necessary
        """
        try:
            token_data = self.redis_client.get('linkedin_token')
            
            if not token_data:
                logger.info("No token found, initiating authentication flow")
                return await self.handle_missing_token()
                
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
                    
            return await self.handle_missing_token()
            
        except json.JSONDecodeError:
            logger.error("Invalid token data in Redis")
            self.redis_client.delete('linkedin_token')
            return await self.handle_missing_token()
            
        except Exception as e:
            logger.error(f"Error in get_valid_token: {str(e)}")
            return None

    async def handle_missing_token(self) -> Optional[str]:
        """
        Handle cases where no valid token exists
        """
        # Store flag indicating authentication is needed
        self.redis_client.setex('linkedin_auth_needed', 300, '1')
        return None

    async def verify_linkedin_comment(self, user_id: str) -> Tuple[bool, str]:
        """
        Verify if a user has commented on the LinkedIn post with their verification code.
        """
        try:
            # Retrieve the stored verification code
            stored_code = self.redis_client.get(f"linkedin_verification_code:{user_id}")
            if not stored_code:
                return False, "Code de vérification non trouvé. Veuillez recommencer."

            stored_code = stored_code.decode('utf-8')
            
            # Get access token
            access_token = await self.get_valid_token()
            if not access_token:
                # Check if authentication is needed
                if self.redis_client.get('linkedin_auth_needed'):
                    return False, "Authentification LinkedIn requise. Un administrateur sera notifié."
                return False, "Erreur de connexion à LinkedIn. Veuillez réessayer plus tard."

            # Make LinkedIn API request
            post_id = "7254038723820949505"
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": "202304"
                }

                try:
                    async with session.get(
                        f"https://api.linkedin.com/v2/socialActions/{post_id}/comments",
                        headers=headers,
                        timeout=10
                    ) as response:
                        if response.status == 401:
                            self.redis_client.delete('linkedin_token')
                            return False, "Session LinkedIn expirée. Un administrateur sera notifié."

                        if response.status != 200:
                            logger.error(f"LinkedIn API error: {response.status}")
                            return False, "Erreur de connexion à LinkedIn. Veuillez réessayer plus tard."

                        data = await response.json()
                        return await self.process_comments(data, stored_code, user_id)

                except aiohttp.ClientError as e:
                    logger.error(f"Network error: {str(e)}")
                    return False, "Erreur de connexion réseau. Veuillez réessayer plus tard."

        except Exception as e:
            logger.error(f"Error verifying LinkedIn comment: {str(e)}")
            return False, "Erreur technique. Veuillez réessayer plus tard."

    async def process_comments(self, data: dict, stored_code: str, user_id: str) -> Tuple[bool, str]:
        """
        Process LinkedIn comments to find verification code
        """
        comments = data.get('elements', [])
        if not comments:
            return False, "Aucun commentaire trouvé. Assurez-vous d'avoir commenté avec le code fourni."

        code_timestamp = self.redis_client.get(f"linkedin_code_timestamp:{user_id}")
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
