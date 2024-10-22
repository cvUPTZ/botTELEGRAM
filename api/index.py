from flask import Flask, request, jsonify, redirect
from telegram import Update
from main import create_application
from config import LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI, REDIS_URL,COMPANY_PAGE_ID, LINKEDIN_ACCESS_TOKEN # Add this to your config
import asyncio
import requests
from jwt import PyJWKClient
import jwt
import json
# from utils.linkedin_utils import exchange_code_for_tokens, check_follow_status
from utils.email_utils import send_email_with_cv
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


@app.route('/start-linkedin-auth/<int:user_id>/<cv_type>/<email>')
def start_linkedin_auth(user_id, cv_type, email):
    auth_url = (
        f"https://www.linkedin.com/oauth/v2/authorization?response_type=code"
        f"&client_id={LINKEDIN_CLIENT_ID}&redirect_uri={LINKEDIN_REDIRECT_URI}"
        f"&state={user_id}|{cv_type}|{email}&scope=openid%20profile%20email"
    )
    return redirect(auth_url)

@app.route('/linkedin-callback')
async def linkedin_callback():
    code = request.args.get('code')
    state = request.args.get('state')

    if not code or not state:
        return "Missing parameters", 400

    try:
        user_id, cv_type, email = state.split('|')
        tokens = await exchange_code_for_tokens(code)
        
        if not tokens.get('access_token'):
            return "Failed to get access token", 400

        verification_status = await verify_linkedin_comment(user_id)
        
        if verification_status:
            # Mark as verified in Redis
            redis_client.set(f"linkedin_verified:{user_id}", "true", ex=3600)
            
            try:
                result = await send_email_with_cv(email, cv_type, int(user_id))
                return "Vérification réussie ! Votre CV a été envoyé. Vous pouvez fermer cette fenêtre et retourner au bot Telegram."
            except Exception as e:
                return f"Erreur lors de l'envoi du CV: {str(e)}", 500
        else:
            return "Code de vérification non trouvé. Assurez-vous d'avoir commenté avec le bon code.", 400

    except Exception as e:
        return f"Une erreur s'est produite: {str(e)}", 500

async def exchange_code_for_tokens(code):
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': LINKEDIN_REDIRECT_URI,
        'client_id': LINKEDIN_CLIENT_ID,
        'client_secret': LINKEDIN_CLIENT_SECRET
    }
    response = await asyncio.to_thread(requests.post, token_url, data=data)
    return response.json()

async def check_linkedin_comment(access_token, post_id, verification_code, user_id):
    # URL for fetching comments from the LinkedIn post
    comments_url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = await asyncio.to_thread(requests.get, comments_url, headers=headers)
    
    if response.status_code == 200:
        comments = response.json().get('elements', [])
        
        # Check if any comment contains the verification code
        for comment in comments:
            actor_id = comment.get('actor', {}).get('id')
            text = comment.get('message', {}).get('text')

            if verification_code in text and str(actor_id) == str(user_id):
                return True

    return False




async def verify_linkedin_code(update, context):
    user_id = update.effective_user.id
    entered_code = context.args[0]

    stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")

    if stored_code and entered_code == stored_code:
        await update.message.reply_text("Code vérifié avec succès. Envoi du CV en cours...")
        await send_email_with_cv(context.args[1], context.args[2], user_id)
    else:
        await update.message.reply_text("❌ Code incorrect ou expiré. Veuillez réessayer.")



if __name__ == "__main__":
    app.run(debug=True)



# async def check_follow_status(access_token, company_id):
#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "X-Restli-Protocol-Version": "2.0.0"
#     }
#     # LinkedIn API to check if a user follows a company (Make sure to have correct permissions)
#     follow_check_url = f"https://api.linkedin.com/v2/me?projection=(followedCompanies)"

#     response = await asyncio.to_thread(requests.get, follow_check_url, headers=headers)
#     data = response.json()

#     if response.status_code == 200:
#         # Check if the user follows the specific company
#         followed_companies = data.get('followedCompanies', [])
#         for company in followed_companies:
#             if company['id'] == str(company_id):
#                 return True
#         return False
#     else:
#         logger.error(f"Error checking follow status: {response.status_code}, {response.text}")
#         return False


if __name__ == "__main__":
    app.run(debug=True)
