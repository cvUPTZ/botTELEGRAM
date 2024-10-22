# linkedin_utils.py

import json
import redis
from config import REDIS_URL, LINKEDIN_ACCESS_TOKEN
import asyncio
redis_client = redis.from_url(REDIS_URL)



async def verify_linkedin_comment(user_id):
    stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
    if not stored_code:
        print(f"No stored verification code found for user {user_id}")
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
            print(f"Retrieved {len(comments)} comments from LinkedIn post")
            
            for comment in comments:
                comment_text = comment.get('message', {}).get('text', '').strip()
                if stored_code in comment_text:
                    print(f"Found matching verification code for user {user_id}")
                    return True
                    
            logger.warning(f"No matching comment found for user {user_id}")
            return False
        else:
            print(f"LinkedIn API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error verifying LinkedIn comment: {str(e)}")
        return False



# async def verify_linkedin_comment(user_id):
#     """
#     Verify if a user has commented on the LinkedIn post with their verification code
#     """
#     try:
#         # LinkedIn post ID from the URL: urn:li:activity:7254038723820949505
#         post_id = "7254038723820949505"
        
#         # Construct the LinkedIn API URL for fetching comments
#         api_url = f"https://api.linkedin.com/rest/socialActions/urn:li:share:{post_id}/comments"
        
#         headers = {
#             "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
#             "X-Restli-Protocol-Version": "2.0.0",
#             "LinkedIn-Version": "202304"
#         }
        
#         # Get the verification code from Redis for this user
#         verification_code = redis_client.get(f"linkedin_verification_code:{user_id}")
#         if not verification_code:
#             print(f"[DEBUG] No verification code found for user {user_id}")
#             return False
            
#         verification_code = verification_code.decode('utf-8') if isinstance(verification_code, bytes) else verification_code
#         print(f"[DEBUG] Verification code for user {user_id}: {verification_code}")
        
#         # Make the API request
#         print(f"[DEBUG] Making LinkedIn API request to: {api_url}")
#         response = await asyncio.to_thread(
#             requests.get,
#             api_url,
#             headers=headers
#         )
        
#         print(f"[DEBUG] LinkedIn API response status: {response.status_code}")
        
#         if response.status_code != 200:
#             print(f"[ERROR] LinkedIn API error: {response.status_code} - {response.text}")
#             return False
            
#         comments_data = response.json()
#         print(f"[DEBUG] LinkedIn API Response: {comments_data}")
        
#         # Check each comment for the verification code
#         elements = comments_data.get('elements', [])
#         for comment in elements:
#             comment_text = comment.get('message', {}).get('text', '')
#             comment_author = comment.get('actor', '')
            
#             print(f"[DEBUG] Checking comment: {comment_text} by {comment_author}")
            
#             if verification_code in comment_text:
#                 print(f"[DEBUG] Found matching verification code in comment")
#                 return True
                
#         print(f"[DEBUG] No matching verification code found in comments")
#         return False
        
#     except Exception as e:
#         print(f"[ERROR] Error verifying LinkedIn comment: {str(e)}")
#         return False

# Update the callback handler in main.py:


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
