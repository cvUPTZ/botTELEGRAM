# bot/handlers.py
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from bot.utils import (start, ask_question, liste_questions, send_cv, my_id,
                       handle_message, tag_all, start_p, help_command, welcome_new_member, offremploi)
from config import BOT_TOKEN


bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("question", ask_question))
bot_app.add_handler(CommandHandler("liste_questions", liste_questions))
bot_app.add_handler(CommandHandler("sendcv", send_cv))
bot_app.add_handler(CommandHandler("myid", my_id))
bot_app.add_handler(CommandHandler("tagall", tag_all))
bot_app.add_handler(CommandHandler("start_p", start_p))
bot_app.add_handler(CommandHandler("help", help_command))
bot_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
