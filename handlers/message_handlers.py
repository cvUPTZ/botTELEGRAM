import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.file_utils import track_user

logger = logging.getLogger(__name__)

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    track_user(user_id, chat_id)
    # Add any additional message handling logic here
    logger.info(f"Received message from user {user_id} in chat {chat_id}: {update.message.text}")