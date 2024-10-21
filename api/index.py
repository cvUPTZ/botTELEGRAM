from flask import Flask, request, jsonify, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI, REDIS_URL
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message
import logging
import json
import requests
import asyncio
from jwt import PyJWKClient
import jwt
import redis

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Flask app
app = Flask(__name__)

# Redis client for storing user information
redis_client = redis.StrictRedis.from_url(REDIS_URL, decode_responses=True)

# Function to create and initialize the application
def create_application():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("question", ask_question))
    application.add_handler(CommandHandler("liste_questions", liste_questions))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CommandHandler("tagall", tag_all))
    application.add_handler(CommandHandler("offremploi", offremploi))        
    application.add_handler(CommandHandler("verify_linkedin", start_linkedin_verification))


    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application

@app.route('/')
def hello():
    return "Hello, World!"

@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.method == "POST":
        # Create and initialize the application for each request
        application = create_application()
        await application.initialize()
        
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        
        # Shutdown the application after processing the update
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
    code = request.args.get('code')
    state = request.args.get('state')  # This is the user_id we passed earlier
    
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
    tokens = response.json()
    access_token = tokens.get('access_token')
    id_token = tokens.get('id_token')
    
    # Decode and verify the ID token
    jwks_client = PyJWKClient("https://www.linkedin.com/oauth/openid/jwks")
    signing_key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, id_token)
    data = jwt.decode(
        id_token,
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
    bot = Application.get_current().bot
    await bot.send_message(chat_id=state, text="LinkedIn verification successful! You can now use all bot features.")
    
    return "Verification successful! You can close this window and return to the Telegram bot."

async def start_linkedin_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    auth_url = f"{LINKEDIN_REDIRECT_URI.replace('/linkedin-callback', '')}/start-linkedin-auth/{user_id}"
    keyboard = [[InlineKeyboardButton("Verify with LinkedIn", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Please click the button below to verify your LinkedIn profile:",
        reply_markup=reply_markup
    )

if __name__ == "__main__":
    app.run(debug=True)


