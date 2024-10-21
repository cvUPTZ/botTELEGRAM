import os
from flask import Flask, request, jsonify, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import json
import requests
import asyncio
from jwt import PyJWKClient
import jwt
from jwt.exceptions import DecodeError, InvalidTokenError
import redis

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID')
LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
LINKEDIN_REDIRECT_URI = os.getenv('LINKEDIN_REDIRECT_URI')
REDIS_URL = os.getenv('REDIS_URL')

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Redis client for storing user information
redis_client = redis.StrictRedis.from_url(REDIS_URL, decode_responses=True)

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Use /verify_linkedin to start the LinkedIn verification process."
    )

async def start_linkedin_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    auth_url = f"{LINKEDIN_REDIRECT_URI.replace('/linkedin-callback', '')}/start-linkedin-auth/{user_id}"
    keyboard = [[InlineKeyboardButton("Verify with LinkedIn", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Please click the button below to verify your LinkedIn profile:",
        reply_markup=reply_markup
    )

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is verified
    user_id = update.effective_user.id
    verified = await asyncio.to_thread(redis_client.exists, f"linkedin_verified:{user_id}")
    
    if not verified:
        await update.message.reply_text("Please verify your LinkedIn profile first using /verify_linkedin")
        return
    
    # Handle the question (placeholder implementation)
    await update.message.reply_text("You asked a question! (This is a placeholder response)")

async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is verified
    user_id = update.effective_user.id
    verified = await asyncio.to_thread(redis_client.exists, f"linkedin_verified:{user_id}")
    
    if not verified:
        await update.message.reply_text("Please verify your LinkedIn profile first using /verify_linkedin")
        return
    
    # Handle CV sending (placeholder implementation)
    await update.message.reply_text("CV sending feature is not implemented yet.")

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Your Telegram ID is: {user_id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # General message handler (placeholder implementation)
    await update.message.reply_text("I received your message, but I'm not sure how to respond.")

# Function to create and initialize the application
def create_application():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    # application.add_handler(CommandHandler("start", start))
    # application.add_handler(CommandHandler("verify_linkedin", start_linkedin_verification))
    # application.add_handler(CommandHandler("question", ask_question))
    # application.add_handler(CommandHandler("sendcv", send_cv))
    # application.add_handler(CommandHandler("myid", my_id))
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("question", ask_question))
    application.add_handler(CommandHandler("liste_questions", liste_questions))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CommandHandler("tagall", tag_all))
    application.add_handler(CommandHandler("offremploi", offremploi))
    application.add_handler(CommandHandler("verify_linkedin", start_linkedin_verification))
    # application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application

# Flask routes
@app.route('/')
def hello():
    return "Hello, World! This is the Telegram Bot Server."

@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.method == "POST":
        application = create_application()
        await application.initialize()
        
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        
        await application.shutdown()
    return jsonify({"status": "ok"})

@app.route('/start-linkedin-auth/<int:user_id>')
async def start_linkedin_auth(user_id):
    auth_url = (
        f"https://www.linkedin.com/oauth/v2/authorization?response_type=code"
        f"&client_id={LINKEDIN_CLIENT_ID}&redirect_uri={LINKEDIN_REDIRECT_URI}"
        f"&state={user_id}&scope=openid%20profile%20email"
    )
    return redirect(auth_url)

@app.route('/linkedin-callback')
async def linkedin_callback():
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        
        # Exchange code for access token and ID token
        token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': LINKEDIN_REDIRECT_URI,
            'client_id': LINKEDIN_CLIENT_ID,
            'client_secret': LINKEDIN_CLIENT_SECRET
        }
        response = await asyncio.to_thread(requests.post, token_url, data=data)
        response.raise_for_status()
        tokens = response.json()
        
        # Log LinkedIn API Response (be careful with sensitive data)
        logger.info("LinkedIn API Response:")
        logger.info(f"Status Code: {response.status_code}")
        logger.info(f"Headers: {response.headers}")
        safe_tokens = {k: v if k not in ['access_token', 'id_token'] else '[REDACTED]' for k, v in tokens.items()}
        logger.info(f"Safe Body: {json.dumps(safe_tokens, indent=2)}")
        
        id_token = tokens.get('id_token')
        if not id_token:
            raise ValueError("No ID token received from LinkedIn")

        logger.info(f"Received ID token type: {type(id_token)}")
        logger.info(f"ID token value: {id_token[:10]}...") # Log first 10 characters for debugging

        # Ensure id_token is bytes
        if isinstance(id_token, str):
            id_token_bytes = id_token.encode('utf-8')
        elif isinstance(id_token, bytes):
            id_token_bytes = id_token
        else:
            raise TypeError(f"Unexpected token type: {type(id_token)}")

        logger.info(f"Converted ID token type: {type(id_token_bytes)}")
        
        # Decode and verify the ID token
        jwks_client = PyJWKClient("https://www.linkedin.com/oauth/openid/jwks")
        signing_key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, id_token_bytes)
        
        data = jwt.decode(
            id_token_bytes,
            signing_key.key,
            algorithms=["RS256"],
            audience=LINKEDIN_CLIENT_ID,
            options={"verify_exp": True},
        )
        
        # Extract user info from the decoded token
        user_info = {
            'sub': data['sub'],
            'email': data.get('email'),
            'name': data.get('name'),
            'picture': data.get('picture')
        }
        
        # Store verification in Redis
        await asyncio.to_thread(redis_client.set, f"linkedin_verified:{state}", json.dumps(user_info))
        
        # Notify user via Telegram
        application = create_application()
        await application.initialize()
        await application.bot.send_message(chat_id=state, text="LinkedIn verification successful! You can now use all bot features.")
        await application.shutdown()
        
        return "Verification successful! You can close this window and return to the Telegram bot."
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during LinkedIn token exchange: {str(e)}")
        return "An error occurred while communicating with LinkedIn. Please try again."
    except ValueError as e:
        logger.error(f"LinkedIn response error: {str(e)}")
        return "Received an invalid response from LinkedIn. Please try again."
    except (DecodeError, InvalidTokenError) as e:
        logger.error(f"JWT decoding error: {str(e)}")
        return "An error occurred while verifying your LinkedIn credentials. Please try again."
    except TypeError as e:
        logger.error(f"Token type error: {str(e)}")
        return "Received an unexpected token type from LinkedIn. Please try again."
    except Exception as e:
        logger.error(f"Unexpected error in LinkedIn callback: {str(e)}", exc_info=True)
        return "An unexpected error occurred. Please try again later."

# Alternative approach: Fetch LinkedIn profile using access token
async def fetch_linkedin_profile(access_token):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'cache-control': 'no-cache',
        'X-Restli-Protocol-Version': '2.0.0'
    }
    
    url = 'https://api.linkedin.com/v2/me'
    
    response = await asyncio.to_thread(requests.get, url, headers=headers)
    response.raise_for_status()
    
    profile_data = response.json()
    
    # Extract relevant information
    user_info = {
        'id': profile_data.get('id'),
        'firstName': profile_data.get('firstName', {}).get('localized', {}).get('en_US'),
        'lastName': profile_data.get('lastName', {}).get('localized', {}).get('en_US'),
        'profilePicture': profile_data.get('profilePicture', {}).get('displayImage')
    }
    
    return user_info

if __name__ == "__main__":
    app.run(debug=True)