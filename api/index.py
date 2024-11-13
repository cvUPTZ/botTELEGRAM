from flask import Flask, request, jsonify, redirect
import aiohttp
from telegram import Update
from main import create_application
from config import (
    LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET,
    LINKEDIN_REDIRECT_URI,
    REDIS_URL
)
import asyncio
import logging
import redis
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import LinkedInVerificationManager, LinkedInTokenManager, LinkedInConfig
from functools import wraps

app = Flask(__name__)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize Redis client
redis_client = redis.StrictRedis.from_url(REDIS_URL, decode_responses=True)

def async_route(f):
    """Decorator to handle async route handlers"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

@app.route('/')
def hello():
    return "Hello, World!"

@app.route('/webhook', methods=['POST'])
@async_route
async def webhook():
    try:
        if request.method == "POST":
            application = create_application()
            await application.initialize()
            update = Update.de_json(request.get_json(force=True), application.bot)
            await application.process_update(update)
            await application.shutdown()
            return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/start-linkedin-auth/<int:user_id>/<cv_type>/<email>')
def start_linkedin_auth(user_id, cv_type, email):
    try:
        # URL encode the state parameters properly
        state = f"{user_id}|{cv_type}|{email}"
        auth_url = (
            f"https://www.linkedin.com/oauth/v2/authorization?"
            f"response_type=code"
            f"&client_id={LINKEDIN_CLIENT_ID}"
            f"&redirect_uri={LINKEDIN_REDIRECT_URI}"
            f"&state={state}"
            f"&scope=openid%20profile%20email%20w_member_social"
        )
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"LinkedIn auth error: {str(e)}")
        return "Une erreur s'est produite lors de l'authentification", 500

@app.route('/linkedin-callback')
@async_route
async def linkedin_callback():
    try:
        code = request.args.get('code')
        state = request.args.get('state')

        if not code or not state:
            return "Paramètres manquants", 400

        user_id, cv_type, email = state.split('|')
        
        # Initialize LinkedIn managers
        linkedin_config = LinkedInConfig(
            client_id=LINKEDIN_CLIENT_ID,
            client_secret=LINKEDIN_CLIENT_SECRET,
            redirect_uri=LINKEDIN_REDIRECT_URI
        )
        
        token_manager = LinkedInTokenManager(redis_client, linkedin_config)
        verification_manager = LinkedInVerificationManager(
            redis_client,
            token_manager,
            linkedin_config
        )

        # Exchange code for token and store it
        try:
            tokens = await exchange_code_for_tokens(code)
            if not tokens or not tokens.get('access_token'):
                logger.error("No access token in response")
                return "Échec de l'obtention du token", 400

            token_manager.store_token(
                int(user_id),
                tokens['access_token'],
                tokens.get('expires_in', 3600)  # Default to 1 hour if not specified
            )
        except Exception as e:
            logger.error(f"Token exchange/storage error: {str(e)}")
            return "Échec de l'authentification LinkedIn", 400

        # Verify LinkedIn comment with proper error handling
        try:
            verified, message = await verification_manager.verify_linkedin_comment(int(user_id))
            
            if verified:
                try:
                    await send_email_with_cv(email, cv_type, int(user_id))
                    return (
                        "Vérification réussie ! Votre CV a été envoyé. "
                        "Vous pouvez fermer cette fenêtre et retourner au bot Telegram."
                    )
                except Exception as e:
                    logger.error(f"Email sending error: {str(e)}")
                    return f"Erreur lors de l'envoi du CV: {str(e)}", 500
            else:
                return f"Échec de la vérification: {message}", 400
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            return "Erreur lors de la vérification LinkedIn", 400

    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        return f"Une erreur s'est produite: {str(e)}", 500

async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for access tokens"""
    try:
        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': LINKEDIN_REDIRECT_URI,
            'client_id': LINKEDIN_CLIENT_ID,
            'client_secret': LINKEDIN_CLIENT_SECRET
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data) as response:
                response_text = await response.text()
                if response.status != 200:
                    logger.error(f"Token exchange failed with status {response.status}: {response_text}")
                    raise Exception(f"Token exchange failed: {response_text}")
                
                try:
                    return await response.json()
                except Exception as e:
                    logger.error(f"Failed to parse token response: {response_text}")
                    raise Exception(f"Invalid token response: {str(e)}")
                
    except Exception as e:
        logger.error(f"Token exchange error: {str(e)}")
        raise

if __name__ == "__main__":
    app.run(debug=True)
