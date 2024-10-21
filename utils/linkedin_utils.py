# linkedin_utils.py

import json
import redis
from config import REDIS_URL

redis_client = redis.from_url(REDIS_URL)

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