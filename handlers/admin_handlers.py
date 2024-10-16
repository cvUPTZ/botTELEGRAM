import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import admin_only
from utils.file_utils import load_questions, save_questions, load_scraped_data

logger = logging.getLogger(__name__)

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

@admin_only
async def offremploi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Fetching job offers, please wait...')

    try:
        data = load_scraped_data()
        
        if not data:
            await update.message.reply_text('No job offers found.')
        else:
            for index, text in enumerate(data):
                message = f'Job Offer {index + 1}: {text}\n\n🔵 Les candidats intéressés, envoyez vos candidatures à l\'adresse suivante :\n📩 : candidat@triemploi.com'
                await update.message.reply_text(message)

    except Exception as e:
        logger.error(f'Unexpected error in offremploi: {e}')
        await update.message.reply_text('❌ An unexpected error occurred. Please try again later.')