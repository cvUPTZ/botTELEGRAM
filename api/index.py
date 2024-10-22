from flask import Flask, request, jsonify, redirect
from telegram import Update
from main import create_application
from config import LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI, REDIS_URL,COMPANY_PAGE_ID
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
    # Construct the LinkedIn OAuth URL with user_id, cv_type, and email in the state parameter
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

    if state is None:
        return "State parameter is missing", 400

    try:
        user_id, cv_type, email = state.split('|')
    except ValueError:
        return "Invalid state format", 400

    tokens = await exchange_code_for_tokens(code)
    access_token = tokens.get('access_token')

    if not access_token:
        return "Access token not received", 400

    if await check_follow_status(access_token, COMPANY_PAGE_ID):
        # User follows the company page, mark as verified
        redis_client.set(f"linkedin_verified:{user_id}", "true")
        
        # Send CV automatically
        try:
            result = await send_email_with_cv(email, cv_type, int(user_id))
            await bot.send_message(chat_id=user_id, text=result)
        except Exception as e:
            error_message = f"Une erreur s'est produite lors de l'envoi du CV: {str(e)}"
            await bot.send_message(chat_id=user_id, text=error_message)
        
        return "Vérification réussie ! Votre CV a été envoyé. Vous pouvez fermer cette fenêtre et retourner au bot Telegram."
    else:
        follow_url = f"https://www.linkedin.com/company/{COMPANY_PAGE_ID}/"
        return redirect(follow_url)

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
    tokens = response.json()
    return tokens

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



async def verify_comment_on_linkedin(update, context, access_token):
    user_id = update.effective_user.id
    verification_code = redis_client.get(f"linkedin_verification_code:{user_id}")
    post_id = "7254038723820949505"  # Replace with the actual LinkedIn post ID
    
    if verification_code and await check_linkedin_comment(access_token, post_id, verification_code, user_id):
        await update.message.reply_text("Vérification réussie ! Envoi du CV en cours...")
        await send_email_with_cv(context.args[1], context.args[2], user_id)
    else:
        await update.message.reply_text("❌ Vérification échouée. Aucun commentaire valide trouvé ou code incorrect.")


async def verify_linkedin_code(update, context):
    user_id = update.effective_user.id
    entered_code = context.args[0]

    stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")

    if stored_code and entered_code == stored_code:
        await update.message.reply_text("Code vérifié avec succès. Envoi du CV en cours...")
        await send_email_with_cv(context.args[1], context.args[2], user_id)
    else:
        await update.message.reply_text("❌ Code incorrect ou expiré. Veuillez réessayer.")

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
