import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from config import EMAIL_ADDRESS, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT, CV_FILES
from utils.file_utils import load_sent_emails, save_sent_emails

logger = logging.getLogger(__name__)

async def send_email_with_cv(email, cv_type, user_id):
    if cv_type.lower() not in CV_FILES:
        return '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".'
    
    sent_emails = load_sent_emails()
    
    # Check if either email or user_id has already received a CV
    if email in sent_emails or str(user_id) in sent_emails:
        return '📩 Vous avez déjà reçu un CV. Vous êtes limité à un seul type de CV par utilisateur et par email. 🚫'
    
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
        
        # Store both email and user_id as keys in the sent_emails dictionary
        sent_emails[email] = cv_type
        sent_emails[str(user_id)] = cv_type
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
