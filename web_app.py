# web_app.py

from flask import Flask, request, redirect, url_for
import requests
import json
from config import LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI, LINKEDIN_SCOPE
import redis
from telegram import Bot
from config import BOT_TOKEN, REDIS_URL, WEBHOOK_URL

app = Flask(__name__)
redis_client = redis.from_url(REDIS_URL)
bot = Bot(token=BOT_TOKEN)

@app.route('/start-linkedin-auth/<int:user_id>')
def start_linkedin_auth(user_id):
    auth_url = f"https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id={LINKEDIN_CLIENT_ID}&redirect_uri={LINKEDIN_REDIRECT_URI}&state={user_id}&scope={LINKEDIN_SCOPE}"
    return redirect(auth_url)

@app.route('/linkedin-callback')
def linkedin_callback():
    code = request.args.get('code')
    state = request.args.get('state')  # This is the user_id we passed earlier
    
    # Exchange code for access token
    token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': LINKEDIN_REDIRECT_URI,
        'client_id': LINKEDIN_CLIENT_ID,
        'client_secret': LINKEDIN_CLIENT_SECRET
    }
    response = requests.post(token_url, data=data)
    access_token = response.json().get('access_token')
    
    # Get user profile
    profile_url = 'https://api.linkedin.com/v2/me'
    headers = {'Authorization': f'Bearer {access_token}'}
    profile_response = requests.get(profile_url, headers=headers)
    profile = profile_response.json()
    
    # Store verification in Redis
    redis_client.set(f"linkedin_verified:{state}", json.dumps(profile))
    
    # Notify user via Telegram
    bot.send_message(chat_id=state, text="LinkedIn verification successful! You can now use all bot features.")
    
    return "Verification successful! You can close this window and return to the Telegram bot."

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    # Process the update here
    return 'OK'

if __name__ == '__main__':
    app.run(ssl_context='adhoc')  # Use 'adhoc' for development, proper SSL cert for production