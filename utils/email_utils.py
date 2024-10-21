import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from config import EMAIL_ADDRESS, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT, CV_FILES, ADMIN_IDS,
    LINKEDIN_REDIRECT_URI
from utils.file_utils import load_sent_emails, save_sent_emails
# from utils.file_utils import load_sent_emails, save_sent_emails
from utils.linkedin_utils import is_linkedin_verified

logger = logging.getLogger(__name__)
 
async def send_email_with_cv(email, cv_type, user_id):
    if cv_type.lower() not in CV_FILES:
        return '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".'
    
    sent_emails = load_sent_emails()
    
    # Check if the user is an admin
    is_admin = user_id in ADMIN_IDS
    
    # Only check for existing emails if the user is not an admin
    if not is_admin:
        user_entry = sent_emails.get(email) or sent_emails.get(str(user_id))
        
        if user_entry:
            if user_entry['cv_type'] == cv_type:
                return f'📩 Vous avez déjà reçu un CV de type {cv_type}. Vous ne pouvez pas en demander un autre du même type.'
            else:
                return f'📩 Vous avez déjà reçu un CV de type {user_entry["cv_type"]}. Vous ne pouvez pas demander un CV de type différent.'
    
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
        
        # Store the sent email info only for non-admin users
        if not is_admin:
            user_data = {'cv_type': cv_type, 'email': email, 'user_id': str(user_id)}
            sent_emails[email] = user_data
            sent_emails[str(user_id)] = user_data
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
