# bot/utils.py
import os
import json
import smtplib
import re
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import asyncio
from config import (EMAIL_ADDRESS, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT,
                    CV_FILES, QUESTIONS_FILE, SENT_EMAILS_FILE, SCRAPED_DATA_FILE,
                    admin_user_ids)

def load_sent_emails():
    if os.path.exists(SENT_EMAILS_FILE):
        with open(SENT_EMAILS_FILE, 'r') as file:
            return json.load(file)
    return {}

def save_sent_emails(sent_emails):
    with open(SENT_EMAILS_FILE, 'w') as file:
        json.dump(sent_emails, file, indent=4)

def load_questions():
    if os.path.exists(QUESTIONS_FILE):
        with open(QUESTIONS_FILE, 'r') as file:
            data = json.load(file)
            next_id = max(map(int, data.keys()), default=0) + 1
            return data, next_id
    return {}, 1

def save_questions(questions):
    with open(QUESTIONS_FILE, 'w') as file:
        json.dump(questions, file, indent=4)

def is_admin(update):
    return update.message.from_user.id in admin_user_ids

questions, next_id = load_questions()
sent_emails = load_sent_emails()
interacted_users = {}

async def start(update, context):
    await update.message.reply_text('👋 Bonjour ! Utilisez /question pour poser une question, /liste_questions pour voir et répondre aux questions (réservé aux administrateurs), ou /sendcv pour recevoir un CV. 📄')

async def ask_question(update, context):
    global next_id
    if len(context.args) == 0:
        await update.message.reply_text('❗ Veuillez fournir votre question.')
        return

    question_text = ' '.join(context.args)
    user_id = update.message.from_user.id

    questions[next_id] = {
        'user_id': user_id,
        'question': question_text,
        'answered': False
    }

    next_id += 1
    save_questions(questions)

    await update.message.reply_text('✅ Votre question a été soumise et sera répondue par un administrateur. 🙏')

async def liste_questions(update, context):
    if not is_admin(update):
        await update.message.reply_text('🚫 Vous n\'êtes pas autorisé à utiliser cette commande.')
        return

    if len(context.args) == 0:
        unanswered_questions = [f'❓ ID: {qid}, Question: {q["question"]}' for qid, q in questions.items() if not q['answered']]

        if not unanswered_questions:
            await update.message.reply_text('🟢 Aucune question non répondue.')
        else:
            await update.message.reply_text('\n'.join(unanswered_questions))
    else:
        if len(context.args) < 2:
            await update.message.reply_text('❗ Veuillez fournir l\'ID de la question et la réponse.')
            return

        question_id = int(context.args[0])
        answer_text = ' '.join(context.args[1:])

        if question_id not in questions or questions[question_id]['answered']:
            await update.message.reply_text('❌ La question n\'existe pas ou a déjà été répondue.')
            return

        questions[question_id]['answer'] = answer_text
        questions[question_id]['answered'] = True

        save_questions(questions)

        await update.message.reply_text(f'✅ La question ID {question_id} a été répondue. ✍️')

async def send_cv(update, context):
    topic_id = 3137
    if update.message.message_thread_id != topic_id:
        await update.message.reply_text('🚫 Cette commande est restreinte au topic CV_UP إحصل على نموذج السيرة')
        return
    
    full_input = ' '.join(context.args)

    if not full_input:
        await update.message.reply_text(
            '❌ Format de commande incorrect. Utilisez :\n'
            '/sendcv [email], [junior|senior]\n\n'
            'Exemple : /sendcv email@gmail.com, junior\n'
            '👉 Assurez-vous d\'inclure une virgule entre l\'email et le type de CV.'
        )
        return

    try:
        email, cv_type = map(str.strip, full_input.split(','))
    except ValueError:
        await update.message.reply_text(
            '❌ Format d\'argument invalide. Utilisez :\n'
            '/sendcv [email], [junior|senior]\n\n'
            'Exemple : /sendcv email@gmail.com, junior\n'
            '👉 Vérifiez que vous avez inclus une virgule entre l\'email et le type de CV.'
        )
        return

    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?$'

    if not re.match(email_regex, email):
        await update.message.reply_text(
            '❌ Format d\'email invalide. Veuillez fournir un email valide.\n'
            'Exemple : email@gmail.com\n'
            '👉 Vérifiez que l\'adresse email ne contient pas d\'espaces supplémentaires ou de caractères invalides.'
        )
        return

    cv_type = cv_type.lower()
    if cv_type not in CV_FILES:
        await update.message.reply_text(
            '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".\n'
            'Exemples :\n'
            '/sendcv email@gmail.com, junior\n'
            '/sendcv email@gmail.com, senior\n'
            '👉 Vérifiez l\'orthographe et assurez-vous de ne pas utiliser d\'espaces supplémentaires.'
        )
        return

    if email in sent_emails:
        await update.message.reply_text(
            '📩 Vous êtes limités à un seul type de CV. 🚫'
        )
        return

    if not os.path.exists(CV_FILES[cv_type]):
        await update.message.reply_text('❌ Le fichier CV n\'existe pas. Veuillez vérifier le type de CV.')
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = f'{cv_type.capitalize()} CV'

        part = MIMEBase('application', 'octet-stream')
        with open(CV_FILES[cv_type], 'rb') as file:
            part.set_payload(file.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={cv_type}_cv.docx')
        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email, msg.as_string())

        sent_emails[email] = cv_type
        save_sent_emails(sent_emails)

        await update.message.reply_text(
           f'✅ Le CV de type {cv_type.capitalize()} a été envoyé à {email}. ✉️\n\n'
           'سعداء جدا باهتمامكم بمبادرة CV_UP ! 🌟\n\n'
           'لقد تحصلتم على نسخة من مودال CV_UP التي ستساعدكم في تفادي أغلب الأخطاء التي قد تحرمكم من فرص العمل. 📝\n\n'
           'بقي الآن تعديلها وفقًا لمعلوماتكم. ✍️\n\n'
           '📄 ملاحظة: لا تنسوا دفع ثمن السيرة الذاتية إما بالتبرع بالدم في إحدى المستشفيات 🩸 أو التبرع بمبلغ من المال إلى جمعية البركة الجزائرية 💵، الذين بدورهم يوصلون التبرعات إلى غزة. 🙏\n\n'
           ' نرجو منكم تأكيد تسديد ثمن النسخة والذي كان التبرع بالدم في أحد المستشفيات أو التبرع لغزة عن طريق جمعية البركة. على الحساب   التالي CCP. 210 243 29 Clé 40 🏥✊'
        )

    except Exception as e:
        logging.error(f'Erreur lors de l\'envoi de l\'e-mail : {e}')
        await update.message.reply_text('❌ Erreur lors de l\'envoi de l\'e-mail. Veuillez réessayer.')

async def my_id(update, context):
    user_id = update.message.from_user.id
    await update.message.reply_text(f'🔍 Votre ID est : {user_id}')

def track_user(update):
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id

    if chat_id not in interacted_users:
        interacted_users[chat_id] = set()

    interacted_users[chat_id].add(user_id)

async def handle_message(update, context):
    track_user(update)

async def tag_all(update, context):
    if not is_admin(update):
        await update.message.reply_text('🚫 Vous n\'êtes pas autorisé à utiliser cette commande.')
        return

    if not context.args:
        await update.message.reply_text('❗ Veuillez fournir un message à envoyer.')
        return

    message = ' '.join(context.args)
    chat_id = update.effective_chat.id

    if chat_id not in interacted_users:
        await update.message.reply_text('❗ Aucun utilisateur à taguer trouvé.')
        return

    user_ids = list(interacted_users[chat_id])
    member_tags = [f'[{user_id}](tg://user?id={user_id})' for user_id in user_ids]

    try:
        for i in range(0, len(member_tags), 5):
            group = member_tags[i:i+5]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{message}\n\n{' '.join(group)}",
                parse_mode='Markdown'
            )
            await asyncio.sleep(1)
        
        await update.message.reply_text('✅ Tous les membres ont été tagués avec succès.')
    except Exception as e:
        await update.message.reply_text(f'❌ Une erreur s\'est produite : {str(e)}')

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

async def start_p(update, context):
    await update.message.reply_text('Welcome to the Resume Analyzer Bot! Send me a resume file (.docx or .pdf) to analyze.')

async def help_command(update, context):
    await update.message.reply_text('Upload a .docx or .pdf file of a resume, and I will analyze it for you!')

async def offremploi(update, context):
    topic_id = 3148
    if update.message.message_thread_id != topic_id:
        await update.message.reply_text('🚫 Cette commande est restreinte au topic CV_UP عروض العمل')
        return
    
    if not is_admin(update):
        await update.message.reply_text('🚫 You are not authorized to use this command.')
        return

    chat_id = update.message.chat_id

    await update.message.reply_text('Fetching job offers, please wait...')

    try:
        if os.path.exists(SCRAPED_DATA_FILE):
            with open(SCRAPED_DATA_FILE, 'r') as file:
                data = json.load(file)
            
            if not data:
                await update.message.reply_text('No job offers found.')
            else:
                for index, text in enumerate(data):
                    message = f'Job Offer {index + 1}: {text}\n\n🔵 Les candidats intéressés, envoyez vos candidatures à l\'adresse suivante :\n📩 : candidat@triemploi.com'
                    await update.message.reply_text(message)
        else:
            await update.message.reply_text('No job offers available yet. Please wait for an admin to update the data.')

    except json.JSONDecodeError:
        logging.error(f'Error decoding JSON from {SCRAPED_DATA_FILE}')
        await update.message.reply_text('❌ Error reading job offers data. Please contact an administrator.')

    except Exception as e:
        logging.error(f'Unexpected error in offremploi: {e}')
        await update.message.reply_text('❌ An unexpected error occurred. Please try again later.')

