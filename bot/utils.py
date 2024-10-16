import json
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from config import (EMAIL_ADDRESS, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT,
                    CV_FILES, QUESTIONS_FILE, SENT_EMAILS_FILE, SCRAPED_DATA_FILE)

logger = logging.getLogger(__name__)

def load_json_file(filename):
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_json_file(filename, data):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)

def load_questions():
    questions = load_json_file(QUESTIONS_FILE)
    next_id = max(map(int, questions.keys()), default=0) + 1
    return questions, next_id

def save_questions(questions):
    save_json_file(QUESTIONS_FILE, questions)

def load_sent_emails():
    return load_json_file(SENT_EMAILS_FILE)

def save_sent_emails(sent_emails):
    save_json_file(SENT_EMAILS_FILE, sent_emails)

def load_scraped_data():
    return load_json_file(SCRAPED_DATA_FILE)

async def send_email_with_cv(email, cv_type):
    if cv_type.lower() not in CV_FILES:
        return '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".'

    sent_emails = load_sent_emails()
    if email in sent_emails:
        return '📩 Vous êtes limités à un seul type de CV. 🚫'

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = f'{cv_type.capitalize()} CV'

        part = MIMEBase('application', 'octet-stream')
        with open(CV_FILES[cv_type.lower()], 'rb') as file:
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

        return (f'✅ Le CV de type {cv_type.capitalize()} a été envoyé à {email}. ✉️\n\n'
                'سعداء جدا باهتمامكم بمبادرة CV_UP ! 🌟\n\n'
                'لقد تحصلتم على نسخة من مودال CV_UP التي ستساعدكم في تفادي أغلب الأخطاء التي قد تحرمكم من فرص العمل. 📝\n\n'
                'بقي الآن تعديلها وفقًا لمعلوماتكم. ✍️\n\n'
                '📄 ملاحظة: لا تنسوا دفع ثمن السيرة الذاتية إما بالتبرع بالدم في إحدى المستشفيات 🩸 أو التبرع بمبلغ من المال إلى جمعية البركة الجزائرية 💵، الذين بدورهم يوصلون التبرعات إلى غزة. 🙏\n\n'
                ' نرجو منكم تأكيد تسديد ثمن النسخة والذي كان التبرع بالدم في أحد المستشفيات أو التبرع لغزة عن طريق جمعية البركة. على الحساب   التالي CCP. 210 243 29 Clé 40 🏥✊')

    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        return f'❌ Erreur lors de l\'envoi de l\'e-mail : {str(e)}'

def track_user(user_id, chat_id):
    # Implement user tracking logic here
    pass