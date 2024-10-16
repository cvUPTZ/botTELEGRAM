import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils import (load_questions, save_questions, load_sent_emails, save_sent_emails,
                       send_email_with_cv, track_user, load_scraped_data)
from bot.decorators import admin_only, private_chat_only

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text('👋 Bonjour ! Utilisez /question pour poser une question, /liste_questions pour voir et répondre aux questions (réservé aux administrateurs), ou /sendcv pour recevoir un CV. 📄')

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir votre question.')
        return

    question_text = ' '.join(context.args)
    user_id = update.effective_user.id

    questions, next_id = load_questions()
    questions[str(next_id)] = {
        'user_id': user_id,
        'question': question_text,
        'answered': False
    }
    save_questions(questions)

    await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    track_user(update) 


@admin_only
async def liste_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    questions, _ = load_questions()
    if not context.args:
        unanswered_questions = [f'❓ ID: {qid}, Question: {q["question"]}' for qid, q in questions.items() if not q['answered']]
        if not unanswered_questions:
            await update.message.reply_text('🟢 Aucune question non répondue.')
        else:
            await update.message.reply_text('\n'.join(unanswered_questions))
    else:
        question_id = context.args[0]
        answer_text = ' '.join(context.args[1:])
        
        if question_id not in questions or questions[question_id]['answered']:
            await update.message.reply_text('❌ La question n\'existe pas ou a déjà été répondue.')
            return

        questions[question_id]['answer'] = answer_text
        questions[question_id]['answered'] = True
        save_questions(questions)

        await update.message.reply_text(f'✅ La question ID {question_id} a été répondue. ✍️')

@private_chat_only
async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            '❌ Format de commande incorrect. Utilisez :\n'
            '/sendcv [email] [junior|senior]\n\n'
            'Exemple : /sendcv email@gmail.com junior'
        )
        return

    email, cv_type = context.args

    result = await send_email_with_cv(email, cv_type)
    await update.message.reply_text(result)

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

@admin_only
async def tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir un message à envoyer.')
        return

    message = ' '.join(context.args)
    chat_id = update.effective_chat.id

    # Implement logic to get all users in the chat
    # This is a placeholder and needs to be implemented based on your tracking logic
    user_ids = []  # Replace with actual user IDs

    if not user_ids:
        await update.message.reply_text('❗ Aucun utilisateur à taguer trouvé.')
        return

    member_tags = [f'[User](tg://user?id={user_id})' for user_id in user_ids]

    for i in range(0, len(member_tags), 5):
        group = member_tags[i:i+5]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{message}\n\n{' '.join(group)}",
            parse_mode='Markdown'
        )

    await update.message.reply_text('✅ Tous les membres ont été tagués avec succès.')

async def welcome_new_member(update, context):
    for new_member in update.message.new_chat_members:
        await update.message.reply_text(
            f"Welcome {new_member.mention_html()}! 👋\n\n"
            "🌟 CV_UP is an initiative aimed at assisting Algerian youth in securing job positions by helping them design their CVs and prepare for job interviews. 📄💼\n\n"
            "Here's our group policy:\n"
            "1. Be respectful to all members. 🤝\n"
            "2. No spam or self-promotion. 🚫\n"
            "3. Use the commands below to interact with the bot. 🤖\n\n"
            "Available commands:\n"
            "/start - Get started with the bot\n"
            "/question [your question] - Ask a question (e.g., /question How do I improve my CV?)\n"
            "/sendcv [email], [junior|senior] - Request a CV (e.g., /sendcv email@example.com, junior)\n"
            "/myid - Get your Telegram user ID\n\n"
            "Enjoy your stay! 😊\n\n"
            "--------------------\n\n"
            f"مرحبًا {new_member.mention_html()}! 👋\n\n"
            "🌟 مبادرة CV_UP هي مبادرة تهدف لمرافقة الشباب الجزائري للحصول على مناصب شغل بمساعدتهم في تصميم السير الذاتية و تحضير مقابلات العمل. 📄💼\n\n"
            "إليك سياسة مجموعتنا:\n"
            "١. احترم جميع الأعضاء. 🤝\n"
            "٢. ممنوع الرسائل غير المرغوب فيها أو الترويج الذاتي. 🚫\n"
            "٣. استخدم الأوامر أدناه للتفاعل مع البوت. 🤖\n\n"
            "الأوامر المتاحة:\n"
            "/start - ابدأ استخدام البوت\n"
            "/question [سؤالك] - اطرح سؤالاً (مثال: /question كيف يمكنني تحسين سيرتي الذاتية؟)\n"
            "/sendcv [البريد الإلكتروني], [junior|senior] - اطلب سيرة ذاتية (مثال: /sendcv email@example.com, junior)\n"
            "/myid - احصل على معرف المستخدم الخاص بك على تيليجرام\n\n"
            "نتمنى لك إقامة طيبة! 😊",
            parse_mode='HTML'
        )
