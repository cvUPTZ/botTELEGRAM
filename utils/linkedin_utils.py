# linkedin_utils.py

import json
import redis
from config import REDIS_URL, LINKEDIN_ACCESS_TOKEN

redis_client = redis.from_url(REDIS_URL)



async def verify_linkedin_comment(user_id):
    stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
    if not stored_code:
        logger.error(f"No stored verification code found for user {user_id}")
        return False

    try:
        post_id = "7254038723820949505"  # Your LinkedIn post ID
        comments_url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "X-Restli-Protocol-Version": "2.0.0"
        }
        
        response = await asyncio.to_thread(
            requests.get, 
            comments_url, 
            headers=headers
        )
        
        if response.status_code == 200:
            comments = response.json().get('elements', [])
            logger.info(f"Retrieved {len(comments)} comments from LinkedIn post")
            
            for comment in comments:
                comment_text = comment.get('message', {}).get('text', '').strip()
                if stored_code in comment_text:
                    logger.info(f"Found matching verification code for user {user_id}")
                    return True
                    
            logger.warning(f"No matching comment found for user {user_id}")
            return False
        else:
            logger.error(f"LinkedIn API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error verifying LinkedIn comment: {str(e)}")
        return False

def is_linkedin_verified(user_id):
    """Check if a user has completed LinkedIn verification."""
    verified_data = redis_client.get(f"linkedin_verified:{user_id}")
    return bool(verified_data)

def get_linkedin_profile(user_id):
    """Get the LinkedIn profile data for a verified user."""
    verified_data = redis_client.get(f"linkedin_verified:{user_id}")
    if verified_data:
        return json.loads(verified_data)
    return None
