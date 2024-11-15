import asyncio
import logging
import signal
import os
from datetime import datetime
import json
import re
from typing import Dict, Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from hypercorn.asyncio import serve
from hypercorn.config import Config
from quart import Quart
from dash import Dash, html
import motor.motor_asyncio

from config import (
    BOT_TOKEN,
    MONGODB_URI,
    EMAIL_ADDRESS,
    EMAIL_PASSWORD,
    SMTP_SERVER,
    SMTP_PORT,
    CV_FILES,
    ADMIN_USER_IDS
)

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize MongoDB
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = client.cvbot
sent_emails_collection = db.sent_emails
questions_collection = db.questions

# Initialize the Dash app
dash_app = Dash(__name__)
dash_app.layout = html.Div("CV Bot Dashboard")

# Create a Quart server
server = Quart(__name__)
dash_app.server = server

# Configure Hypercorn
config = Config()
config.bind = [f"0.0.0.0:{os.environ.get('PORT', 10000)}"]
config.use_reloader = False
config.workers = 1

# Global control flag
bot_running = True

class CVBot:
    def __init__(self, token: str):
        self.token = token
        self.application = None
        
    async def setup(self):
        """Initialize and setup the bot application"""
        self.application = Application.builder().token(self.token).build()
        
        # Register command handlers
        handlers = [
            CommandHandler("start", self.start),
            CommandHandler("question", self.ask_question),
            CommandHandler("liste_questions", self.liste_questions),
            CommandHandler("sendcv", self.send_cv),  # The handler registration remains the same
            CommandHandler("myid", self.my_id),
            CommandHandler("tagall", self.tag_all),
            CommandHandler("offremploi", self.offremploi),
            MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.welcome_new_member),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        ]
        
        for handler in handlers:
            self.application.add_handler(handler)
            
        await self.application.initialize()
        
    async def start_polling(self):
        """Start the bot polling for updates"""
        await self.application.start()
        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    async def shutdown(self):
        """Properly shutdown the bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    # Command Handlers
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        logger.info(f"Start command received from user {update.effective_user.id}")
        try:
            await update.message.reply_text(
                '👋 Bonjour ! Voici les commandes disponibles :\n\n'
                '/question - Poser une question\n'
                '/liste_questions - Voir et répondre aux questions (réservé aux administrateurs)\n'
                '/sendcv - Recevoir un CV\n'
                '/myid - Voir votre ID'
            )
            logger.info("Start message sent successfully")
        except Exception as e:
            logger.error(f"Error sending start message: {str(e)}")

    async def ask_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /question command"""
        if not context.args:
            await update.message.reply_text('❗ Veuillez fournir votre question.')
            return

        question_text = ' '.join(context.args)
        user_id = update.effective_user.id

        try:
            # Insert question into MongoDB
            await questions_collection.insert_one({
                'user_id': user_id,
                'question': question_text,
                'answered': False,
                'timestamp': datetime.utcnow()
            })

            await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')
        except Exception as e:
            logger.error(f"Error saving question: {str(e)}")
            await update.message.reply_text('❌ Une erreur est survenue lors de l\'enregistrement de votre question.')

    async def liste_questions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /liste_questions command (admin only)"""
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text('❌ Cette commande est réservée aux administrateurs.')
            return

        try:
            questions = await questions_collection.find({'answered': False}).to_list(length=None)
            if not questions:
                await update.message.reply_text('📝 Aucune question en attente.')
                return

            response = "Questions en attente :\n\n"
            for q in questions:
                response += f"ID: {str(q['_id'])}\n"
                response += f"Question: {q['question']}\n"
                response += f"User ID: {q['user_id']}\n\n"

            await update.message.reply_text(response)
        except Exception as e:
            logger.error(f"Error listing questions: {str(e)}")
            await update.message.reply_text('❌ Une erreur est survenue lors de la récupération des questions.')

    @staticmethod
    async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /sendcv command"""
        try:
            if not context.args or len(context.args) != 2:
                await update.message.reply_text(
                    '❌ Format: /sendcv [email] [junior|senior]\n'
                    'Exemple: /sendcv email@example.com junior'
                )
                return

            email = context.args[0].lower()
            cv_type = context.args[1].lower()

            # Validate email format
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                await update.message.reply_text('❌ Format d\'email invalide.')
                return

            # Validate CV type
            if cv_type not in ['junior', 'senior']:
                await update.message.reply_text('❌ Type de CV invalide. Utilisez "junior" ou "senior".')
                return

            user_id = update.effective_user.id
            is_admin = user_id in ADMIN_USER_IDS

            # Check previous sends for non-admin users
            if not is_admin:
                # Check if email has already received a CV
                email_record = await sent_emails_collection.find_one({"email": email})
                if email_record:
                    await update.message.reply_text(
                        f'📩 Cet email a déjà reçu un CV de type {email_record["cv_type"]}.'
                    )
                    return

                # Check if user has already received a CV
                user_record = await sent_emails_collection.find_one({"user_id": str(user_id)})
                if user_record:
                    await update.message.reply_text(
                        f'📩 Vous avez déjà reçu un CV de type {user_record["cv_type"]}.'
                    )
                    return

            # Send email with CV
            from utils.email_utils import send_email_with_cv
            result = await send_email_with_cv(
                email=email,
                cv_type=cv_type,
                user_id=user_id,
                context=context
            )
            
            await update.message.reply_text(result)

        except Exception as e:
            logger.error(f"Error in send_cv: {str(e)}", exc_info=True)
            await update.message.reply_text('❌ Une erreur est survenue lors de l\'envoi du CV.')

    async def my_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /myid command"""
        user_id = update.effective_user.id
        await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

    async def tag_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /tagall command (admin only)"""
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text('❌ Cette commande est réservée aux administrateurs.')
            return

        try:
            chat_members = await context.bot.get_chat_administrators(update.effective_chat.id)
            member_list = [member.user.mention_html() for member in chat_members]
            await update.message.reply_html("🔔 " + " ".join(member_list))
        except Exception as e:
            logger.error(f"Error in tag_all: {str(e)}")
            await update.message.reply_text('❌ Une erreur est survenue.')

    async def offremploi(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /offremploi command (admin only)"""
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text('❌ Cette commande est réservée aux administrateurs.')
            return

        if not context.args:
            await update.message.reply_text('❗ Veuillez fournir le texte de l\'offre d\'emploi.')
            return

        offer_text = ' '.join(context.args)
        try:
            await update.message.reply_text(
                f"💼 Nouvelle offre d'emploi !\n\n{offer_text}",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error in offremploi: {str(e)}")
            await update.message.reply_text('❌ Une erreur est survenue lors de la publication de l\'offre.')

    async def welcome_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new member joins"""
        try:
            for member in update.message.new_chat_members:
                if not member.is_bot:
                    await update.message.reply_text(
                        f"👋 Bienvenue {member.mention_html()} !\n\n"
                        "Utilisez /start pour voir les commandes disponibles.",
                        parse_mode='HTML'
                    )
        except Exception as e:
            logger.error(f"Error in welcome_new_member: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        # Add your message handling logic here
        pass

def signal_handler(sig, frame):
    """Handle system signals for graceful shutdown"""
    global bot_running
    logger.info("Shutting down gracefully...")
    bot_running = False

@server.route('/')
async def hello():
    """Basic health check endpoint"""
    return "CV Bot is running!"

async def run_dash():
    """Run the Dash dashboard"""
    await serve(server, config)

async def run_telegram_bot(bot_token: str):
    """Run the Telegram bot"""
    bot = CVBot(bot_token)
    try:
        await bot.setup()
        await bot.start_polling()
        
        while bot_running:
            await asyncio.sleep(1)
            
        await bot.shutdown()
        
    except Exception as e:
        logger.error(f"Bot error: {str(e)}", exc_info=True)
        await bot.shutdown()

async def main():
    """Main entry point"""
    # Set up signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, signal_handler)
    
    # Run both the Dash app and Telegram bot
    dash_task = asyncio.create_task(run_dash())
    telegram_task = asyncio.create_task(run_telegram_bot(BOT_TOKEN))
    
    try:
        await asyncio.gather(dash_task, telegram_task)
    except Exception as e:
        logger.error(f"Main loop error: {str(e)}", exc_info=True)
    finally:
        global bot_running
        bot_running = False

if __name__ == '__main__':
    asyncio.run(main())
