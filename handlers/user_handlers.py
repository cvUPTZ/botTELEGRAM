import time
import random
import string
import logging
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from utils.decorators import private_chat_only
from utils.email_utils import send_email_with_cv
from utils.linkedin_utils import verify_linkedin_comment
from config import (
    ADMIN_USER_IDS,
    QUESTIONS_TABLE,
    SENT_EMAILS_TABLE,
    USERS_TABLE,
    REDIS_URL
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL)

@private_chat_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command"""
    logger.info(f"Start command received from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            '👋 Bonjour ! Voici les commandes disponibles :\n\n'
            '/question - Poser une question\n'
            '/liste_questions - Voir et répondre aux questions (réservé aux administrateurs)\n'
            '/sendcv - Recevoir un CV (nécessite de suivre notre page LinkedIn)\n'
            '📄 N\'oubliez pas de suivre notre page LinkedIn avant de demander un CV !'
        )
        logger.info("Start message sent successfully")
    except Exception as e:
        logger.error(f"Error sending start message: {str(e)}")
        await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")

@private_chat_only
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /question command"""
    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir votre question.')
        return

    question_text = ' '.join(context.args)
    user_id = update.effective_user.id

    try:
        # Store question in Supabase
        await context.bot.supabase.table(QUESTIONS_TABLE).insert({
            "user_id": user_id,
            "question": question_text,
            "answered": False,
            "answer": None
        }).execute()
        
        logger.info(f"Question saved successfully for user {user_id}")
        await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')
    
    except Exception as e:
        logger.error(f"Error saving question to Supabase: {str(e)}")
        await update.message.reply_text('❌ Une erreur s\'est produite. Veuillez réessayer plus tard.')

@private_chat_only
async def list_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /liste_questions command (admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text('❌ Cette commande est réservée aux administrateurs.')
        return
        
    try:
        # Fetch unanswered questions from Supabase
        response = await context.bot.supabase.table(QUESTIONS_TABLE)\
            .select('*')\
            .eq('answered', False)\
            .execute()
        
        questions = response.data
        
        if not questions:
            await update.message.reply_text('📭 Aucune question en attente.')
            return
            
        for question in questions:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Répondre", callback_data=f"answer_{question['id']}"),
                    InlineKeyboardButton("❌ Supprimer", callback_data=f"delete_{question['id']}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Question de {question['user_id']}:\n\n"
                f"{question['question']}",
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"Error listing questions: {str(e)}")
        await update.message.reply_text('❌ Une erreur s\'est produite lors de la récupération des questions.')
        
@private_chat_only
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /sendcv command"""
    try:
        user_id = update.effective_user.id
        
        if len(context.args) != 2:
            await update.message.reply_text(
                '❌ Format incorrect. Utilisez:\n'
                '/sendcv [email] [junior|senior]\n'
                'Exemple: /sendcv email@example.com junior'
            )
            return
        
        email, cv_type = context.args
        cv_type = cv_type.lower()
        
        if cv_type not in ['junior', 'senior']:
            await update.message.reply_text('❌ Type de CV incorrect. Utilisez "junior" ou "senior".')
            return
        
        # Admin bypass for LinkedIn verification
        if user_id in ADMIN_USER_IDS:
            try:
                result = await send_email_with_cv(
                    email, 
                    cv_type, 
                    user_id, 
                    context.application.supabase
                )
                await update.message.reply_text(result)
                return
            except Exception as e:
                logger.error(f"Error sending CV for admin {user_id}: {str(e)}")
                await update.message.reply_text(f"❌ Erreur: {str(e)}")
                return

        # Generate verification code with timestamp
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        current_time = time.time()
        
        # Store verification data in Redis with timestamp
        redis_client.setex(f"linkedin_verification_code:{user_id}", 3600, verification_code)
        redis_client.setex(f"linkedin_code_timestamp:{user_id}", 3600, str(current_time))
        redis_client.setex(f"linkedin_email:{user_id}", 3600, email)
        redis_client.setex(f"linkedin_cv_type:{user_id}", 3600, cv_type)
        
        # Check if user has already received a CV in the past
        try:
            response = await context.application.supabase.table(SENT_EMAILS_TABLE)\
                .select('*')\
                .filter('email', 'eq', email)\
                .execute()

            if response.data:
                previous_send = response.data[0]
                if previous_send['cv_type'] == cv_type:
                    await update.message.reply_text(f'📩 Vous avez déjà reçu un CV de type {cv_type}.')
                    return
                else:
                    await update.message.reply_text(f'📩 Vous avez déjà reçu un CV de type {previous_send["cv_type"]}.')
                    return
        except Exception as e:
            logger.error(f"Error checking previous CV sends: {str(e)}")
        
        linkedin_post_url = "https://www.linkedin.com/feed/update/urn:li:activity:7254038723820949505"
        
        keyboard = [
            [InlineKeyboardButton("📝 Voir la publication LinkedIn", url=linkedin_post_url)],
            [InlineKeyboardButton("✅ J'ai commenté", callback_data=f"verify_{verification_code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Pour recevoir votre CV, veuillez suivre ces étapes dans l'ordre :\n\n"
            f"1. Cliquer sur le bouton ci-dessous pour voir la publication\n"
            f"2. Suivre notre page LinkedIn\n"
            f"3. Commenter avec exactement ce code : {verification_code}\n"
            f"4. Revenir ici et cliquer sur 'J'ai commenté'\n\n"
            f"⚠️ Important:\n"
            f"- Le code est valide pendant 1 heure\n"
            f"- Vous devez suivre les étapes dans l'ordre\n"
            f"- Les commentaires faits avant la génération du code ne sont pas valides\n"
            f"- Un seul CV par adresse email",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in send_cv command: {str(e)}")
        await update.message.reply_text("❌ Une erreur s'est produite. Veuillez réessayer plus tard.")


async def handle_linkedin_verification(query, user_id, context):
    """Handle LinkedIn verification process"""
    try:
        # Retrieve stored data from Redis
        stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
        stored_email = redis_client.get(f"linkedin_email:{user_id}")
        stored_cv_type = redis_client.get(f"linkedin_cv_type:{user_id}")
        
        # Decode bytes to strings and handle missing data
        stored_data = {
            'code': stored_code.decode('utf-8') if stored_code else None,
            'email': stored_email.decode('utf-8') if stored_email else None,
            'cv_type': stored_cv_type.decode('utf-8') if stored_cv_type else None
        }
        
        logger.info(f"Retrieved stored data for user {user_id}: {stored_data}")
        
        if not all(stored_data.values()):
            await query.message.edit_text("❌ Session expirée. Veuillez recommencer avec /sendcv")
            return
        
        verification_code = query.data.split("_")[1]
        if verification_code != stored_data['code']:
            await query.message.edit_text("❌ Code de vérification invalide. Veuillez réessayer avec /sendcv")
            return
        
        await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")
        
        comment_verified = await verify_linkedin_comment(user_id)
        if not comment_verified:
            await query.message.edit_text(
                "❌ Commentaire non trouvé. Assurez-vous d'avoir commenté avec le bon code sur la publication LinkedIn."
            )
            return
        
        await query.message.edit_text("✅ Commentaire vérifié. Envoi du CV en cours...")
        
        try:
            result = await send_email_with_cv(
                stored_data['email'], 
                stored_data['cv_type'], 
                user_id,
                context.bot.supabase
            )
            
            # Clean up Redis data
            redis_keys = [
                f"linkedin_verification_code:{user_id}",
                f"linkedin_email:{user_id}",
                f"linkedin_cv_type:{user_id}"
            ]
            redis_client.delete(*redis_keys)
            
            await query.message.edit_text(f"✅ Vérification réussie!\n{result}")
            
        except Exception as e:
            logger.error(f"Error sending CV: {str(e)}")
            await query.message.edit_text(
                "❌ Une erreur s'est produite lors de l'envoi du CV. Veuillez réessayer avec /sendcv"
            )
            
    except Exception as e:
        logger.error(f"Error in LinkedIn verification: {str(e)}")
        await query.message.edit_text(
            "❌ Une erreur s'est produite. Veuillez réessayer avec /sendcv"
        )

async def handle_answer_question(query, context):
    """Handle admin answering a question"""
    question_id = query.data.split("_")[1]
    
    try:
        # Get the question from Supabase
        response = await context.bot.supabase.table(QUESTIONS_TABLE)\
            .select('*')\
            .eq('id', question_id)\
            .single()\
            .execute()
            
        question = response.data
        
        if not question:
            await query.message.edit_text("❌ Question non trouvée.")
            return
            
        # Store the question ID in user data for the next step
        context.user_data['answering_question'] = question_id
        
        await query.message.edit_text(
            f"📝 Répondez à cette question:\n\n"
            f"{question['question']}\n\n"
            "Envoyez votre réponse dans le prochain message."
        )
        
    except Exception as e:
        logger.error(f"Error handling answer question: {str(e)}")
        await query.message.edit_text("❌ Une erreur s'est produite.")

async def handle_delete_question(query, context):
    """Handle admin deleting a question"""
    question_id = query.data.split("_")[1]
    
    try:
        # Delete the question from Supabase
        await context.bot.supabase.table(QUESTIONS_TABLE)\
            .delete()\
            .eq('id', question_id)\
            .execute()
            
        await query.message.edit_text("✅ Question supprimée.")
        
    except Exception as e:
        logger.error(f"Error deleting question: {str(e)}")
        await query.message.edit_text("❌ Une erreur s'est produite lors de la suppression.")
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        await query.answer()
        
        if query.data.startswith("verify_"):
            verification_code = query.data.split("_")[1]
            redis_client = context.application.redis_client
            
            # Retrieve stored data
            stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
            stored_email = redis_client.get(f"linkedin_email:{user_id}")
            stored_cv_type = redis_client.get(f"linkedin_cv_type:{user_id}")
            
            stored_data = {
                'code': stored_code.decode('utf-8') if stored_code else None,
                'email': stored_email.decode('utf-8') if stored_email else None,
                'cv_type': stored_cv_type.decode('utf-8') if stored_cv_type else None
            }
            
            if not all(stored_data.values()):
                await query.message.edit_text("❌ Session expirée. Veuillez recommencer avec /sendcv")
                return
            
            if verification_code != stored_data['code']:
                await query.message.edit_text("❌ Code de vérification invalide. Veuillez réessayer avec /sendcv")
                return
            
            await query.message.edit_text("🔄 Vérification du commentaire LinkedIn en cours...")
            
            comment_verified = await verify_linkedin_comment(user_id)
            if not comment_verified:
                await query.message.edit_text(
                    "❌ Commentaire non trouvé. Assurez-vous d'avoir commenté avec le bon code."
                )
                return
            
            await query.message.edit_text("✅ Commentaire vérifié. Envoi du CV en cours...")
            
            try:
                result = await send_email_with_cv(
                    stored_data['email'],
                    stored_data['cv_type'],
                    user_id,
                    context.application.supabase
                )
                
                # Clean up Redis data
                redis_keys = [
                    f"linkedin_verification_code:{user_id}",
                    f"linkedin_email:{user_id}",
                    f"linkedin_cv_type:{user_id}"
                ]
                redis_client.delete(*redis_keys)
                
                await query.message.edit_text(result)
                
            except Exception as e:
                logger.error(f"Error sending CV: {str(e)}")
                await query.message.edit_text(
                    "❌ Une erreur s'est produite lors de l'envoi du CV. Veuillez réessayer."
                )
    
    except Exception as e:
        logger.error(f"Error in callback handler: {str(e)}")
        await query.message.edit_text("❌ Une erreur s'est produite. Veuillez réessayer.")


@private_chat_only
async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /myid command"""
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

def setup_handlers(application):
    """Set up all command handlers"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sendcv", send_cv))
    application.add_handler(CommandHandler("myid", my_id))
    application.add_handler(CommandHandler("question", ask_question))
    application.add_handler(CommandHandler("liste_questions", list_questions))
    application.add_handler(CallbackQueryHandler(callback_handler))
