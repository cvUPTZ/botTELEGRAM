from flask import Flask, request, jsonify, redirect
from telegram import Update
from main import create_application
from config import LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI, REDIS_URL
import asyncio
import requests
from jwt import PyJWKClient
import jwt
import json
import redis

app = Flask(__name__)

# Redis client for storing user information
redis_client = redis.StrictRedis.from_url(REDIS_URL, decode_responses=True)

@app.route('/')
def hello():
    return "Hello, World!"

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
def start_linkedin_auth(user_id):
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
    id_token = tokens.get('id_token')

    # Convert the id_token to bytes
    id_token_bytes = id_token.encode('utf-8') if isinstance(id_token, str) else id_token
    
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

if __name__ == "__main__":
    app.run(debug=True)