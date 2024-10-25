# api/index.py
from flask import Flask, request, jsonify, redirect
from telegram import Update
from main import create_application
import logging
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/webhook', methods=['POST'])
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

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/linkedin-callback')
async def linkedin_callback():
    try:
        code = request.args.get('code')
        state = request.args.get('state')

        if not code or not state:
            return "Missing parameters", 400

        application = create_application()
        await application.initialize()
        
        # Process OAuth callback
        result = await application.linkedin_manager.authenticate_user(code)
        if not result or not result.get('access_token'):
            return "Failed to obtain access token", 400

        # Store the token
        user_id = int(state)
        await application.linkedin_manager.store_access_token(
            user_id,
            result['access_token'],
            result['expires_in']
        )

        await application.shutdown()
        return "Authentication successful! You can close this window."

    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        return f"An error occurred: {str(e)}", 500
