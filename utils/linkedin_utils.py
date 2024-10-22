# linkedin_utils.py

import json
import redis
import asyncio
import requests
import logging
from datetime import datetime, timedelta
from config import REDIS_URL, LINKEDIN_ACCESS_TOKEN

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = redis.from_url(REDIS_URL)

class LinkedInError(Exception):
    """Custom exception for LinkedIn API errors"""
    pass

async def refresh_linkedin_token():
    """
    Implement token refresh logic here if you have refresh token flow
    For now, just logs the error
    """
    logger.error("LinkedIn token needs to be refreshed or renewed")
    return False

async def verify_linkedin_comment(user_id: str) -> bool:
    """
    Verify if a user has commented on the LinkedIn post with their verification code
    
    Args:
        user_id (str): The user ID to verify
        
    Returns:
        bool: True if verification successful, False otherwise
        
    Raises:
        LinkedInError: If there's an error communicating with LinkedIn API
    """
    stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
    
    if not stored_code:
        logger.warning(f"No stored verification code found for user {user_id}")
        return False
        
    stored_code = stored_code.decode('utf-8') if isinstance(stored_code, bytes) else stored_code
    
    try:
        post_id = "7254038723820949505"
        comments_url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
        
        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
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
                    timeout=10  # Add timeout
                )
                
                if response.status_code == 401:
                    # Token might be expired
                    if await refresh_linkedin_token():
                        # Retry with new token
                        retry_count += 1
                        continue
                    else:
                        raise LinkedInError("Unable to refresh LinkedIn access token")
                        
                response.raise_for_status()
                
                comments = response.json().get('elements', [])
                logger.info(f"Retrieved {len(comments)} comments from LinkedIn post")
                
                # Store successful response in cache
                cache_key = f"linkedin_comments_cache:{post_id}"
                redis_client.setex(
                    cache_key,
                    timedelta(minutes=5),  # Cache for 5 minutes
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
                        
                        return True
                
                logger.warning(f"No matching comment found for user {user_id}")
                return False
                
            except requests.exceptions.RequestException as e:
                retry_count += 1
                if retry_count == max_retries:
                    raise LinkedInError(f"Network error after {max_retries} retries: {str(e)}")
                await asyncio.sleep(1)  # Wait before retry
                
    except Exception as e:
        logger.error(f"Error verifying LinkedIn comment: {str(e)}", exc_info=True)
        raise LinkedInError(f"Failed to verify LinkedIn comment: {str(e)}")

def is_linkedin_verified(user_id: str) -> bool:
    """
    Check if a user has completed LinkedIn verification
    
    Args:
        user_id (str): The user ID to check
        
    Returns:
        bool: True if verified, False otherwise
    """
    verified_data = redis_client.get(f"linkedin_verified:{user_id}")
    if not verified_data:
        return False
        
    try:
        data = json.loads(verified_data)
        verified_at = datetime.fromisoformat(data['verified_at'])
        # Verification valid for 30 days
        return datetime.utcnow() - verified_at <= timedelta(days=30)
    except (json.JSONDecodeError, KeyError, ValueError):
        return False

def get_linkedin_profile(user_id: str) -> dict:
    """
    Get the LinkedIn profile data for a verified user
    
    Args:
        user_id (str): The user ID to get profile for
        
    Returns:
        dict: Profile data if verified, None otherwise
    """
    verified_data = redis_client.get(f"linkedin_verified:{user_id}")
    if verified_data:
        try:
            return json.loads(verified_data)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON data for user {user_id}")
    return None
