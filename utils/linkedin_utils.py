import logging
import asyncio
import secrets
import string
from urllib.parse import quote
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LinkedInError(Exception):
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

class LinkedInErrorCode:
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_REQUEST = "INVALID_REQUEST"
    API_ERROR = "API_ERROR"
    REDIS_ERROR = "REDIS_ERROR"

class RedisManager:
    def __init__(self, redis_url: str, max_retries: int = 3):
        self.redis_url = redis_url
        self.max_retries = max_retries
        self._redis: Optional[Redis] = None
        self._lock = asyncio.Lock()

    async def get_connection(self) -> Redis:
        async with self._lock:
            if self._redis is None:
                try:
                    # Create a connection pool with redis.asyncio
                    self._redis = Redis.from_url(self.redis_url)
                    # Test the connection
                    await self._redis.ping()
                except RedisError as e:
                    logger.error(f"Failed to connect to Redis: {e}")
                    raise LinkedInError("Redis connection failed", LinkedInErrorCode.REDIS_ERROR)
            return self._redis

    async def execute(self, operation, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                redis = await self.get_connection()
                # Dynamically execute the requested Redis operation
                method = getattr(redis, operation)
                return await method(*args, **kwargs)
            except (ConnectionError, RedisError) as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Redis operation failed after {self.max_retries} attempts: {e}")
                    raise LinkedInError("Redis operation failed", LinkedInErrorCode.REDIS_ERROR)
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                self._redis = None  # Force reconnection

class LinkedInConfig:
    def __init__(self, 
                 client_id: str, 
                 client_secret: str, 
                 redirect_uri: str, 
                 post_url: str,
                 access_token: str, 
                 scope: str, 
                 company_page_id: int, 
                 post_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.post_url = post_url
        self.access_token = access_token
        self.scope = scope
        self.company_page_id = company_page_id
        self.post_id = post_id

class LinkedInTokenManager:
    def __init__(self, redis_manager: RedisManager, config: LinkedInConfig):
        self.redis_manager = redis_manager
        self.config = config
        self.token_key_prefix = "linkedin_token:"
        self.token_expiry_prefix = "linkedin_token_expiry:"
        self.refresh_token_prefix = "linkedin_refresh_token:"

    async def get_token(self, user_id: int) -> Optional[str]:
        try:
            token = await self.redis_manager.execute(
                'get', 
                f"{self.token_key_prefix}{user_id}"
            )
            if not token:
                return None

            expiry = await self.redis_manager.execute(
                'get',
                f"{self.token_expiry_prefix}{user_id}"
            )
            if not expiry or float(expiry) < datetime.utcnow().timestamp():
                return None

            return token
        except LinkedInError:
            logger.error(f"Error getting token for user {user_id}")
            return None

    async def store_token(self, user_id: int, access_token: str, expires_in: int, refresh_token: Optional[str] = None):
        try:
            expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            
            redis = await self.redis_manager.get_connection()
            async with redis.pipeline() as pipe:
                pipe.setex(f"{self.token_key_prefix}{user_id}", expires_in, access_token)
                pipe.setex(f"{self.token_expiry_prefix}{user_id}", expires_in, expiry.timestamp())
                if refresh_token:
                    pipe.set(f"{self.refresh_token_prefix}{user_id}", refresh_token)
                await pipe.execute()
        except LinkedInError as e:
            logger.error(f"Error storing token: {e}")
            raise

class LinkedInAPI:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.linkedin.com/v2"
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json'
        }
        self._client = None

    async def __aenter__(self):
        if self._client is None:
            self._client = httpx.AsyncClient(headers=self.headers, timeout=30)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def get_post_comments(self, post_id: str) -> list:
        for attempt in range(3):  # Max 3 retries
            try:
                url = f"{self.base_url}/socialActions/{quote(post_id, safe='')}/comments"
                response = await self._client.get(url)

                if response.status_code == 429:  # Rate limit
                    wait_time = int(response.headers.get('Retry-After', 60))
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                data = response.json()

                return [
                    {
                        'text': comment.get('message', {}).get('text', ''),
                        'actor': comment.get('actor', ''),
                        'created': comment.get('created', {}).get('time')
                    }
                    for comment in data.get('elements', [])
                ]

            except httpx.HTTPError as e:
                logger.error(f"API request failed (attempt {attempt + 1}/3): {e}")
                if attempt == 2:  # Last attempt
                    raise LinkedInError(f"API request failed: {e}", LinkedInErrorCode.API_ERROR)
                await asyncio.sleep(2 ** attempt)

        return []



class LinkedInVerificationManager:
    def __init__(self, redis_manager: Redis, config: LinkedInConfig, verification_ttl: int = 3600):
        self.redis_manager = redis_manager
        self.config = config
        self.verification_ttl = verification_ttl
        self.prefix = "linkedin_verification:"
        self._api = None

    @property
    async def api(self):
        if self._api is None:
            self._api = LinkedInAPI(self.config.access_token)
        return self._api

    async def generate_verification_code(self, user_id: int) -> str:
        try:
            while True:
                code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
                key = f"{self.prefix}code:{code}"
                
                exists = await self.redis_manager.exists(key)
                if not exists:
                    await self.redis_manager.setex(key, self.verification_ttl, str(user_id))
                    return code
        except LinkedInError as e:
            logger.error(f"Error generating verification code: {e}")
            raise

    async def verify_linkedin_comment(self, user_id: int, verification_code: str, post_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        try:
            # Check verification attempts
            attempts_key = f"{self.prefix}attempts:{user_id}"
            attempts = await self.redis_manager.incr(attempts_key)
            
            if attempts == 1:
                await self.redis_manager.expire(attempts_key, self.verification_ttl)
            
            if attempts > 3:  # Max 3 attempts
                return False, "❌ Too many attempts. Please try again later.", None

            # Verify code
            code_key = f"{self.prefix}code:{verification_code}"
            stored_user_id = await self.redis_manager.get(code_key)
            
            if not stored_user_id or int(stored_user_id) != user_id:
                return False, "❌ Invalid or expired verification code.", None

            # Check comments
            api = await self.api
            comments = await api.get_post_comments(post_id)
            
            for comment in comments:
                if verification_code in comment['text']:
                    return True, "✅ Verification successful!", comment

            return False, "❌ Code not found in recent comments. Please try again.", None

        except LinkedInError as e:
            logger.error(f"Verification error: {e}")
            return False, f"❌ Error: {e.message}", None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False, "❌ An unexpected error occurred.", None

class LinkedInAuthManager:
    def __init__(self, 
                 redis_manager: RedisManager,
                 token_manager: LinkedInTokenManager, 
                 config: LinkedInConfig):
        self.redis_manager = redis_manager
        self.token_manager = token_manager
        self.config = config
        self.state_prefix = "linkedin_auth_state:"
        self.state_ttl = 600  # 10 minutes

    async def generate_auth_url(self, user_id: int) -> str:
        try:
            # Generate state parameter for CSRF protection
            state = secrets.token_urlsafe(32)
            
            # Store state with user_id in Redis
            await self.redis_manager.execute(
                'setex',
                f"{self.state_prefix}{state}",
                self.state_ttl,
                str(user_id)
            )
            
            # Build the LinkedIn authorization URL
            params = {
                'response_type': 'code',
                'client_id': self.config.client_id,
                'redirect_uri': self.config.redirect_uri,
                'state': state,
                'scope': self.config.scope
            }
            
            query_string = '&'.join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
            return f"https://www.linkedin.com/oauth/v2/authorization?{query_string}"
            
        except LinkedInError as e:
            logger.error(f"Error generating auth URL: {str(e)}")
            raise LinkedInError("Failed to generate authorization URL", LinkedInErrorCode.REDIS_ERROR)

    async def validate_state(self, state: str) -> Optional[int]:
        try:
            # Retrieve the user_id from Redis based on the state
            user_id = await self.redis_manager.execute('get', f"{self.state_prefix}{state}")
            if not user_id:
                return None
            
            # Clean up the used state from Redis
            await self.redis_manager.execute('delete', f"{self.state_prefix}{state}")
            
            return int(user_id)
            
        except LinkedInError as e:
            logger.error(f"Error validating state: {str(e)}")
            return None

    async def handle_oauth_callback(self, code: str, state: str) -> Tuple[bool, str, Optional[int]]:
        try:
            # Validate state parameter
            user_id = await self.validate_state(state)
            if not user_id:
                return False, "❌ Invalid or expired session.", None

            # Exchange the authorization code for tokens using httpx
            async with httpx.AsyncClient() as client:
                data = {
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret,
                    'redirect_uri': self.config.redirect_uri
                }
                
                response = await client.post('https://www.linkedin.com/oauth/v2/accessToken', data=data)

                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"Token exchange failed: {error_text}")
                    return False, "❌ LinkedIn authentication failed.", user_id
                    
                # Parse the JSON response
                result = response.json()

                # Store the access token and other relevant info
                await self.token_manager.store_token(
                    user_id=user_id,
                    access_token=result['access_token'],
                    expires_in=result['expires_in'],
                    refresh_token=result.get('refresh_token')
                )
                
                return True, "✅ LinkedIn authentication successful!", user_id
        
        except LinkedInError as e:
            # Catch specific LinkedIn errors
            logger.error(f"LinkedIn error during OAuth callback: {str(e)}")
            return False, f"❌ Authentication error: {e.message}", None
        
        except Exception as e:
            # Catch any unexpected exceptions
            logger.error(f"Unexpected error during OAuth callback: {str(e)}")
            return False, "❌ An unexpected error occurred.", None

# from redis.asyncio import Redis

def create_linkedin_managers(redis_url: str, config: LinkedInConfig) -> Tuple[LinkedInTokenManager, LinkedInVerificationManager, LinkedInAuthManager]:
    try:
        # Initialize Redis manager
        redis_manager = RedisManager(redis_url)
        
        # Initialize managers
        token_manager = LinkedInTokenManager(redis_manager, config)
        verification_manager = LinkedInVerificationManager(redis_manager, config)
        auth_manager = LinkedInAuthManager(redis_manager, token_manager, config)
        
        return token_manager, verification_manager, auth_manager
        
    except Exception as e:
        logger.error(f"Error initializing LinkedIn managers: {str(e)}")
        raise

async def main():
    config = LinkedInConfig(
        client_id="your_client_id",
        client_secret="your_client_secret",
        redirect_uri="your_redirect_uri",
        post_url="your_post_url",
        access_token="your_access_token",
        scope="your_scope",
        company_page_id=12345,
        post_id="your_post_id"
    )
    
    token_manager, verification_manager, auth_manager = create_linkedin_managers(
        redis_url="redis://localhost:6379/0",
        config=config
    )
    
    try:
        # Generate auth URL example
        auth_url = await auth_manager.generate_auth_url(user_id=123)
        print(f"Authorization URL: {auth_url}")
        
        # Generate verification code example
        code = await verification_manager.generate_verification_code(user_id=123)
        print(f"Verification code: {code}")
        
        # Verify comment example
        success, message, data = await verification_manager.verify_linkedin_comment(
            user_id=123,
            verification_code=code,
            post_id=config.post_id
        )
        print(f"Verification result: {message}")
        
        if success and data:
            print("Comment data:", data)
            
        # OAuth callback handling example (simulated)
        success, message, user_id = await auth_manager.handle_oauth_callback(
            code="example_oauth_code",
            state="example_state"
        )
        print(f"OAuth callback result: {message}")
        
    except LinkedInError as e:
        print(f"LinkedIn error: {e.message} (Code: {e.code})")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
    finally:
        # Clean up any remaining sessions
        if hasattr(verification_manager, '_api') and verification_manager._api:
            if verification_manager._api._session:
                await verification_manager._api._session.close()

if __name__ == "__main__":
    asyncio.run(main())
