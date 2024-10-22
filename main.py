import asyncio
import logging
import signal
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from handlers.admin_handlers import liste_questions, tag_all, offremploi
from handlers.user_handlers import start, ask_question, send_cv, my_id
from handlers.message_handlers import welcome_new_member, handle_message
from config import BOT_TOKEN, LINKEDIN_CLIENT_ID, LINKEDIN_REDIRECT_URI, REDIS_URL
import redis

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL)

# Global variable to control the bot's running state
bot_running = True

def signal_handler(sig, frame):
    global bot_running
    logger.info("Shutting down gracefully...")
    bot_running = False

# async def start_linkedin_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = update.effective_user.id
#     auth_url = f"{LINKEDIN_REDIRECT_URI.replace('/linkedin-callback', '')}/start-linkedin-auth/{user_id}/{cv_type}"
#     keyboard = [[InlineKeyboardButton("Verify with LinkedIn", url=auth_url)]]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     await update.message.reply_text(
#         "Please click the button below to verify your LinkedIn profile:",
#         reply_markup=reply_markup
#     )

async def start_linkedin_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if cv_type is provided as an argument
    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir le type de CV (junior ou senior).')
        return
    
    cv_type = context.args[0].lower()

    # Validate the CV type
    valid_cv_types = ['junior', 'senior']
    if cv_type not in valid_cv_types:
        await update.message.reply_text(f'❌ Type de CV incorrect. Veuillez utiliser "{valid_cv_types[0]}" ou "{valid_cv_types[1]}".')
        return
    
    # Construct the authentication URL with user_id and cv_type
    auth_url = f"{LINKEDIN_REDIRECT_URI.rstrip('/linkedin-callback')}/start-linkedin-auth/{user_id}/{cv_type}"
    
    # Create an inline button that directs to the LinkedIn auth page
    keyboard = [[InlineKeyboardButton("Vérifiez avec LinkedIn", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send a message with the verification button
    await update.message.reply_text(
        "Veuillez cliquer sur le bouton ci-dessous pour vérifier votre profil LinkedIn :",
        reply_markup=reply_markup
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    
    try:
        await query.answer()
        
        if not query.data.startswith("verify_"):
            return
            
        user_id = update.effective_user.id
        stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
        email = redis_client.get(f"linkedin_email:{user_id}")
        cv_type = redis_client.get(f"linkedin_cv_type:{user_id}")
        
        if not all([stored_code, email, cv_type]):
            await query.message.edit_text("❌ Session expirée. Veuillez recommencer avec /sendcv")
            return
        
        verification_code = query.data.split("_")[1]
        
        # First verify that the code matches
        if verification_code != stored_code:
            await query.message.edit_text("❌ Code de vérification invalide. Veuillez réessayer avec /sendcv")
            return
        
        # Show processing message
        await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")
        
        # Then verify the LinkedIn comment
        comment_verified = await verify_linkedin_comment(user_id)
        if not comment_verified:
            await query.message.edit_text(
                "❌ Commentaire non trouvé. Assurez-vous d'avoir commenté avec le bon code sur la publication LinkedIn."
            )
            return
        
        # Show processing message
        await query.message.edit_text("✅ Commentaire vérifié. Envoi du CV en cours...")
        
        try:
            # Send CV
            result = await send_email_with_cv(email, cv_type, user_id)
            
            # Clear Redis data
            for key in [
                f"linkedin_verification_code:{user_id}",
                f"linkedin_email:{user_id}",
                f"linkedin_cv_type:{user_id}"
            ]:
                redis_client.delete(key)
            
            await query.message.edit_text(f"✅ Vérification réussie!\n{result}")
            
        except Exception as e:
            logger.error(f"Error sending CV: {str(e)}")
            await query.message.edit_text(
                "❌ Une erreur s'est produite lors de l'envoi du CV. Veuillez réessayer avec /sendcv"
            )
            
    except Exception as e:
        logger.error(f"Error in callback handler: {str(e)}")
        try:
            await query.message.edit_text(
                "❌ Une erreur s'est produite. Veuillez réessayer avec /sendcv"
            )
        except Exception as nested_e:
            logger.error(f"Error sending error message: {str(nested_e)}")


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
    application.add_handler(CallbackQueryHandler(callback_handler))  # Added callback handler

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application

async def run_telegram_bot():
    global bot_running
    try:
        application = create_application()
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

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(run_telegram_bot())
