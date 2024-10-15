# import os
# from flask import Flask, request
# from telegram import Update
# from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
# import re
# from sklearn.feature_extraction.text import TfidfVectorizer
# import nltk
# from nltk.tokenize import word_tokenize
# from docx import Document
# import fitz  # PyMuPDF for PDF reading
# import json 
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.base import MIMEBase
# from email import encoders
# import logging
# import asyncio
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.common.keys import Keys
# from datetime import datetime, timedelta

# nltk.download('punkt')

# # Configuration
# EMAIL_ADDRESS = 'cvupdz@gmail.com'
# EMAIL_PASSWORD = 'avpu agry kuwj zlzs'
# SMTP_SERVER = 'smtp.gmail.com'
# SMTP_PORT = 587
# TELEGRAM_BOT_TOKEN = '7495077361:AAGFA9GN6MCoUjNmiWDEUwa7IvN8C7E1dR0'
# WEBHOOK_URL = 'https://your-domain.com/webhook'  # Replace with your actual webhook URL
# PORT = int(os.environ.get('PORT', 5000))

# CV_FILES = {
#     'junior': 'cv_models/Junior_cv_model.docx',
#     'senior': 'cv_models/Senior_cv_model.docx'
# }

# QUESTIONS_FILE = 'questions.json'
# SENT_EMAILS_FILE = 'my_telegram_bot/sent_emails.json'
# SCRAPED_DATA_FILE = 'scraped_linkedin_data.json'

# admin_user_ids = [1719899525, 987654321]  # Replace with actual user IDs

# # Flask app
# app = Flask(__name__)

# # Telegram bot application
# bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# # Helper functions
# def load_sent_emails():
#     if os.path.exists(SENT_EMAILS_FILE):
#         with open(SENT_EMAILS_FILE, 'r') as file:
#             return json.load(file)
#     return {}

# def save_sent_emails(sent_emails):
#     with open(SENT_EMAILS_FILE, 'w') as file:
#         json.dump(sent_emails, file, indent=4)

# def load_questions():
#     if os.path.exists(QUESTIONS_FILE):
#         with open(QUESTIONS_FILE, 'r') as file:
#             data = json.load(file)
#             next_id = max(map(int, data.keys()), default=0) + 1
#             return data, next_id
#     return {}, 1

# def save_questions(questions):
#     with open(QUESTIONS_FILE, 'w') as file:
#         json.dump(questions, file, indent=4)

# def is_admin(update: Update) -> bool:
#     return update.message.from_user.id in admin_user_ids

# questions, next_id = load_questions()
# sent_emails = load_sent_emails()
# interacted_users = {}

# # Command handlers
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     await update.message.reply_text('👋 Bonjour ! Utilisez /question pour poser une question, /liste_questions pour voir et répondre aux questions (réservé aux administrateurs), ou /sendcv pour recevoir un CV. 📄')

# async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     global next_id
#     if len(context.args) == 0:
#         await update.message.reply_text('❗ Veuillez fournir votre question.')
#         return

#     question_text = ' '.join(context.args)
#     user_id = update.message.from_user.id

#     questions[next_id] = {
#         'user_id': user_id,
#         'question': question_text,
#         'answered': False
#     }

#     next_id += 1
#     save_questions(questions)

#     await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')

# async def liste_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     if not is_admin(update):
#         await update.message.reply_text('🚫 Vous n\'êtes pas autorisé à utiliser cette commande.')
#         return

#     if len(context.args) == 0:
#         unanswered_questions = [f'❓ ID: {qid}, Question: {q["question"]}' for qid, q in questions.items() if not q['answered']]

#         if not unanswered_questions:
#             await update.message.reply_text('🟢 Aucune question non répondue.')
#         else:
#             await update.message.reply_text('\n'.join(unanswered_questions))
#     else:
#         if len(context.args) < 2:
#             await update.message.reply_text('❗ Veuillez fournir l\'ID de la question et la réponse.')
#             return

#         question_id = int(context.args[0])
#         answer_text = ' '.join(context.args[1:])

#         if question_id not in questions or questions[question_id]['answered']:
#             await update.message.reply_text('❌ La question n\'existe pas ou a déjà été répondue.')
#             return

#         questions[question_id]['answer'] = answer_text
#         questions[question_id]['answered'] = True

#         save_questions(questions)

#         await update.message.reply_text(f'✅ La question ID {question_id} a été répondue. ✍️')

# async def send_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     topic_id = 3137
#     if update.message.message_thread_id != topic_id:
#         await update.message.reply_text('🚫 Cette commande est restreinte au topic CV_UP إحصل على نموذج السيرة')
#         return
    
#     full_input = ' '.join(context.args)

#     if not full_input:
#         await update.message.reply_text(
#             '❌ Format de commande incorrect. Utilisez :\n'
#             '/sendcv [email], [junior|senior]\n\n'
#             'Exemple : /sendcv email@gmail.com, junior\n'
#             '👉 Assurez-vous d\'inclure une virgule entre l\'email et le type de CV.'
#         )
#         return

#     try:
#         email, cv_type = map(str.strip, full_input.split(','))
#     except ValueError:
#         await update.message.reply_text(
#             '❌ Format d\'argument invalide. Utilisez :\n'
#             '/sendcv [email], [junior|senior]\n\n'
#             'Exemple : /sendcv email@gmail.com, junior\n'
#             '👉 Vérifiez que vous avez inclus une virgule entre l\'email et le type de CV.'
#         )
#         return

#     email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?$'

#     if not re.match(email_regex, email):
#         await update.message.reply_text(
#             '❌ Format d\'email invalide. Veuillez fournir un email valide.\n'
#             'Exemple : email@gmail.com\n'
#             '👉 Vérifiez que l\'adresse email ne contient pas d\'espaces supplémentaires ou de caractères invalides.'
#         )
#         return

#     cv_type = cv_type.lower()
#     if cv_type not in CV_FILES:
#         await update.message.reply_text(
#             '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".\n'
#             'Exemples :\n'
#             '/sendcv email@gmail.com, junior\n'
#             '/sendcv email@gmail.com, senior\n'
#             '👉 Vérifiez l\'orthographe et assurez-vous de ne pas utiliser d\'espaces supplémentaires.'
#         )
#         return

#     if email in sent_emails:
#         await update.message.reply_text(
#             '📩 Vous êtes limités à un seul type de CV. 🚫'
#         )
#         return

#     if not os.path.exists(CV_FILES[cv_type]):
#         await update.message.reply_text('❌ Le fichier CV n\'existe pas. Veuillez vérifier le type de CV.')
#         return

#     try:
#         msg = MIMEMultipart()
#         msg['From'] = EMAIL_ADDRESS
#         msg['To'] = email
#         msg['Subject'] = f'{cv_type.capitalize()} CV'

#         part = MIMEBase('application', 'octet-stream')
#         with open(CV_FILES[cv_type], 'rb') as file:
#             part.set_payload(file.read())
#         encoders.encode_base64(part)
#         part.add_header('Content-Disposition', f'attachment; filename={cv_type}_cv.docx')
#         msg.attach(part)

#         with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
#             server.starttls()
#             server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
#             server.sendmail(EMAIL_ADDRESS, email, msg.as_string())

#         sent_emails[email] = cv_type
#         save_sent_emails(sent_emails)

#         await update.message.reply_text(
#            f'✅ Le CV de type {cv_type.capitalize()} a été envoyé à {email}. ✉️\n\n'
#            'سعداء جدا باهتمامكم بمبادرة CV_UP ! 🌟\n\n'
#            'لقد تحصلتم على نسخة من مودال CV_UP التي ستساعدكم في تفادي أغلب الأخطاء التي قد تحرمكم من فرص العمل. 📝\n\n'
#            'بقي الآن تعديلها وفقًا لمعلوماتكم. ✍️\n\n'
#            '📄 ملاحظة: لا تنسوا دفع ثمن السيرة الذاتية إما بالتبرع بالدم في إحدى المستشفيات 🩸 أو التبرع بمبلغ من المال إلى جمعية البركة الجزائرية 💵، الذين بدورهم يوصلون التبرعات إلى غزة. 🙏\n\n'
#            ' نرجو منكم تأكيد تسديد ثمن النسخة والذي كان التبرع بالدم في أحد المستشفيات أو التبرع لغزة عن طريق جمعية البركة. على الحساب   التالي CCP. 210 243 29 Clé 40 🏥✊'
#         )

#     except Exception as e:
#         logging.error(f'Erreur lors de l\'envoi de l\'e-mail : {e}')
#         await update.message.reply_text('❌ Erreur lors de l\'envoi de l\'e-mail. Veuillez réessayer.')

# async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     user_id = update.message.from_user.id
#     await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

# def track_user(update: Update) -> None:
#     user_id = update.message.from_user.id
#     chat_id = update.effective_chat.id

#     if chat_id not in interacted_users:
#         interacted_users[chat_id] = set()

#     interacted_users[chat_id].add(user_id)

# async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     track_user(update)

# async def tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     if not is_admin(update):
#         await update.message.reply_text('🚫 Vous n\'êtes pas autorisé à utiliser cette commande.')
#         return

#     if not context.args:
#         await update.message.reply_text('❗ Veuillez fournir un message à envoyer.')
#         return

#     message = ' '.join(context.args)
#     chat_id = update.effective_chat.id

#     if chat_id not in interacted_users:
#         await update.message.reply_text('❗ Aucun utilisateur à taguer trouvé.')
#         return

#     user_ids = list(interacted_users[chat_id])
#     member_tags = [f'[{user_id}](tg://user?id={user_id})' for user_id in user_ids]

#     try:
#         for i in range(0, len(member_tags), 5):
#             group = member_tags[i:i+5]
#             await context.bot.send_message(
#                 chat_id=chat_id,
#                 text=f"{message}\n\n{' '.join(group)}",
#                 parse_mode='Markdown'
#             )
#             await asyncio.sleep(1)
        
#         await update.message.reply_text('✅ Tous les membres ont été tagués avec succès.')
#     except Exception as e:
#         await update.message.reply_text(f'❌ Une erreur s\'est produite : {str(e)}')

# async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     for new_member in update.message.new_chat_members:
#         await update.message.reply_text(
#             f"Welcome {new_member.mention_html()}! 👋\n\n"
#             "🌟 CV_UP is an initiative aimed at assisting Algerian youth in securing job positions by helping them design their CVs and prepare for job interviews. 📄💼\n\n"
#             "Here's our group policy:\n"
#             "1. Be respectful to all members. 🤝\n"
#             "2. No spam or self-promotion. 🚫\n"
#             "3. Use the commands below to interact with the bot. 🤖\n\n"
#             "Available commands:\n"
#             "/start - Get started with the bot\n"
#             "/question [your question] - Ask a question (e.g., /question How do I improve my CV?)\n"
#             "/sendcv [email], [junior|senior] - Request a CV (e.g., /sendcv email@example.com, junior)\n"
#             "/myid - Get your Telegram user ID\n\n"
#             "Enjoy your stay! 😊\n\n"
#             "--------------------\n\n"
#             f"مرحبًا {new_member.mention_html()}! 👋\n\n"
#             "🌟 مبادرة CV_UP هي مبادرة تهدف لمرافقة الشباب الجزائري للحصول على مناصب شغل بمساعدتهم في تصميم السير الذاتية و تحضير مقابلات العمل. 📄💼\n\n"
#             "إليك سياسة مجموعتنا:\n"
#             "١. احترم جميع الأعضاء. 🤝\n"
#             "٢. ممنوع الرسائل غير المرغوب فيها أو الترويج الذاتي. 🚫\n"
#             "٣. استخدم الأوامر أدناه للتفاعل مع البوت. 🤖\n\n"
#             "الأوامر المتاحة:\n"
#             "/start - ابدأ استخدام البوت\n"
#             "/question [سؤالك] - اطرح سؤالاً (مثال: /question كيف يمكنني تحسين سيرتي الذاتية؟)\n"
#             "/sendcv [البريد الإلكتروني], [junior|senior] - اطلب سيرة ذاتية (مثال: /sendcv email@example.com, junior)\n"
#             "/myid - احصل على معرف المستخدم الخاص بك على تيليجرام\n\n"
#             "نتمنى لك إقامة طيبة! 😊",
#             parse_mode='HTML'
#         )

# async def start_p(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     await update.message.reply_text('Welcome to the Resume Analyzer Bot! Send me a resume file (.docx or .pdf) to analyze.')

# async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     await update.message.reply_text('Upload a .docx or .pdf file of a resume, and I will analyze it for you!')

# async def analyze_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     if not update.message.document:
#         await update.message.reply_text('Please upload a .docx or .pdf file to analyze.')
#         return

#     file = await context.bot.get_file(update.message.document.file_id)
#     file_name = update.message.document.file_name

#     if not (file_name.endswith('.docx') or file_name.endswith('.pdf')):
#         await update.message.reply_text('Please upload a .docx or .pdf file.')
#         return

#     await update.message.reply_text('Analyzing your resume... Please wait.')

#     download_path = f"temp_{file_name}"
#     await file.download_to_drive(download_path)

#     try:
#         analysis_result = analyze_resume(download_path)
#         assessment = generate_resume_assessment(analysis_result)

#         formatted_result = assessment

#         if len(formatted_result) > 4096:
#             for i in range(0, len(formatted_result), 4096):
#                 await update.message.reply_text(formatted_result[i:i+4096])
#         else:
#             await update.message.reply_text(formatted_result)

#     except Exception as e:
#         await update.message.reply_text(f"An error occurred while analyzing the resume: {str(e)}")

#     finally:
#         if os.path.exists(download_path):
#             os.remove(download_path)

# def scrape_linkedin():
#     chrome_options = Options()
#     chrome_options.add_argument("--no-sandbox")
#     chrome_options.add_argument("--disable-dev-shm-usage")

#     service = Service('chromedriver.exe')  # Replace with your ChromeDriver path
#     driver = webdriver.Chrome(service=service, options=chrome_options)

#     try:
#         driver.get('https://triemploi.com/jobs')

#         elements = WebDriverWait(driver, 20).until(
#             EC.presence_of_all_elements_located((By.CSS_SELECTOR, '#myList > li > div > div.text-col > div > h4 > a'))
#         )

#         data = [element.text.strip() for element in elements]
#         return data

#     except Exception as e:
#         print(f"An error occurred: {e}")
#     finally:
#         driver.quit()

# async def admin_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     if not is_admin(update):
#         await update.message.reply_text('🚫 You are not authorized to use this command.')
#         return

#     chat_id = update.message.chat_id
#     await context.bot.send_message(chat_id=chat_id, text='Starting LinkedIn scraping, please wait...')

#     try:
#         new_data = scrape_linkedin()

#         if os.path.exists(SCRAPED_DATA_FILE):
#             with open(SCRAPED_DATA_FILE, 'r') as file:
#                 existing_data = json.load(file)
#         else:
#             existing_data = []

#         for item in new_data:
#             if item not in existing_data:
#                 existing_data.append(item)

#         with open(SCRAPED_DATA_FILE, 'w') as file:
#             json.dump(existing_data, file, indent=4)

#         await context.bot.send_message(chat_id=chat_id, text=f'Scraped and saved {len(new_data)} items. Total unique items: {len(existing_data)}')

#     except Exception as e:
#         await context.bot.send_message(chat_id=chat_id, text=f'Error during scraping: {str(e)}')

# async def offremploi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     topic_id = 3148
#     if update.message.message_thread_id != topic_id:
#         await update.message.reply_text('🚫 Cette commande est restreinte au topic CV_UP عروض العمل')
#         return
    
#     if not is_admin(update):
#         await update.message.reply_text('🚫 You are not authorized to use this command.')
#         return

#     chat_id = update.message.chat_id

#     await update.message.reply_text('Fetching job offers, please wait...')

#     try:
#         if os.path.exists(SCRAPED_DATA_FILE):
#             with open(SCRAPED_DATA_FILE, 'r') as file:
#                 data = json.load(file)
            
#             if not data:
#                 await update.message.reply_text('No job offers found.')
#             else:
#                 for index, text in enumerate(data):
#                     message = f'Job Offer {index + 1}: {text}\n\n🔵 Les candidats intéressés, envoyez vos candidatures à l\'adresse suivante :\n📩 : candidat@triemploi.com'
#                     await update.message.reply_text(message)
#         else:
#             await update.message.reply_text('No job offers available yet. Please wait for an admin to update the data.')

#     except json.JSONDecodeError:
#         logging.error(f'Error decoding JSON from {SCRAPED_DATA_FILE}')
#         await update.message.reply_text('❌ Error reading job offers data. Please contact an administrator.')

#     except Exception as e:
#         logging.error(f'Unexpected error in offremploi: {e}')
#         await update.message.reply_text('❌ An unexpected error occurred. Please try again later.')

# def generate_resume_assessment(analysis_result):
#     # Your existing generate_resume_assessment function here
#     pass

# def analyze_resume(file_path):
#     # Your existing analyze_resume function here
#     pass

# # Set up handlers
# bot_app.add_handler(CommandHandler("start", start))
# bot_app.add_handler(CommandHandler("question", ask_question))
# bot_app.add_handler(CommandHandler("liste_questions", liste_questions))
# bot_app.add_handler(CommandHandler("sendcv", send_cv))
# bot_app.add_handler(CommandHandler("myid", my_id))
# bot_app.add_handler(CommandHandler("admin_scrape", admin_scrape))
# bot_app.add_handler(CommandHandler("offremploi", offremploi))
# bot_app.add_handler(CommandHandler("tagall", tag_all))
# bot_app.add_handler(CommandHandler("start_p", start_p))
# bot_app.add_handler(CommandHandler("help", help_command))
# bot_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
# bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# @app.route('/webhook', methods=['POST'])
# def webhook():
#     update = Update.de_json(request.get_json(force=True), bot_app.bot)
#     bot_app.process_update(update)
#     return 'OK'

# @app.route('/')
# def index():
#     return 'Hello, World!'

# def main():
#     bot_app.bot.set_webhook(url=WEBHOOK_URL)
#     app.run(host='0.0.0.0', port=PORT)

# if __name__ == '__main__':
#     main()

# app.py
from flask import Flask, request
from telegram import Update
from bot.handler import bot_app
from config import PORT, WEBHOOK_URL

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.process_update(update)
    return 'OK'

@app.route('/')
def index():
    return 'Hello, World!'

def main():
    bot_app.bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    main()