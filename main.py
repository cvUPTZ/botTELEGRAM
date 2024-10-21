import asyncio
import logging
import signal
import sys
import os
import json
import jwt
from jwt import PyJWKClient
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.ext import ContextTypes

from config import BOT_TOKEN, LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI, LINKEDIN_SCOPE, REDIS_URL
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message
from dash import Dash, html
from quart import Quart, request, redirect
from hypercorn.asyncio import serve
from hypercorn.config import Config
import redis

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the Dash app
dash_app = Dash(__name__)
dash_app.layout = html.Div("Hello from Dash!")

# Create a Quart server (asyncio-compatible Flask-like server)
server = Quart(__name__)
dash_app.server = server

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL)

# Configure Hypercorn
config = Config()
config.bind = [f"0.0.0.0:{os.environ.get('PORT', 10000)}"]
config.use_reloader = False
config.workers = 1

# Global variable to control the bot's running state
bot_running = True

def signal_handler(sig, frame):
    global bot_running
    logger.info("Shutting down gracefully...")
    bot_running = False

@server.route('/')
async def hello():
    return "Hello, World!"

@server.route('/start-linkedin-auth/<int:user_id>')
async def start_linkedin_auth(user_id):
    auth_url = f"https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id={LINKEDIN_CLIENT_ID}&redirect_uri={LINKEDIN_REDIRECT_URI}&state={user_id}&scope=openid%20profile%20email"
    print(auth_url)
    return redirect(auth_url)
# https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=78te86nulnq2wk&redirect_uri=https%3A%2F%2Fbot-telegram-pied.vercel.app&state=1719899525&scope=openid%20profile%20email



# @server.route('/start-linkedin-auth/<int:user_id>')
# async def start_linkedin_auth(user_id):
#     return f"Starting LinkedIn auth for user {user_id}"


@server.route('/linkedin-callback')
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
    print(tokens)
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
    aauth_url = f"https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id={LINKEDIN_CLIENT_ID}&redirect_uri={LINKEDIN_REDIRECT_URI}&state={user_id}&scope=openid%20profile%20email"
    

    auth_url = f"{LINKEDIN_REDIRECT_URI.replace('/linkedin-callback', '')}/start-linkedin-auth/{user_id}"
    keyboard = [[InlineKeyboardButton("Verify with LinkedIn", url=auth_url)]]
    print(aauth_url)
    print(auth_url)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Please click the button below to verify your LinkedIn profile:",
        reply_markup=reply_markup
    )

async def run_dash():
    await serve(server, config)

async def run_telegram_bot():
    global bot_running
    try:
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

        await application.initialize()
        await application.start()
        
        # Start polling in a separate task
        polling_task = asyncio.create_task(
            application.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        )

        logger.info("Telegram bot started successfully")
        
        # Keep the bot running until bot_running is set to False
        while bot_running:
            await asyncio.sleep(1)

        # Proper shutdown
        logger.info("Stopping Telegram bot...")
        await polling_task
        await application.stop()
        await application.shutdown()
        
    except Exception as e:
        logger.error("Error running Telegram bot", exc_info=True)

async def main():
    dash_task = asyncio.create_task(run_dash())
    telegram_task = asyncio.create_task(run_telegram_bot())

    await asyncio.gather(dash_task, telegram_task)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())