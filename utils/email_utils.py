import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any
from datetime import datetime
import logging
import json
from config import (
    EMAIL_ADDRESS,
    EMAIL_PASSWORD,
    SMTP_SERVER,
    SMTP_PORT,
    CV_FILES,
    ADMIN_USER_IDS,
    SENT_EMAILS_FILE
)

logger = logging.getLogger(__name__)

def load_sent_emails():
    try:
        with open(SENT_EMAILS_FILE, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.error("Error decoding JSON from sent emails file")
        return {}

def save_sent_emails(sent_emails):
    try:
        with open(SENT_EMAILS_FILE, 'w') as file:
            json.dump(sent_emails, file, indent=4)
    except Exception as e:
        logger.error(f"Error saving sent emails: {str(e)}")

async def send_email_with_cv(email: str, cv_type: str, user_id: int) -> str:
    """Send CV via email and track sending history"""
    if cv_type.lower() not in CV_FILES:
        return '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".'
    
    is_admin = user_id in ADMIN_USER_IDS
    
    try:
        # Load existing sent emails
        sent_emails = load_sent_emails()
        
        # Check previous sends for non-admin users
        if not is_admin:
            # Check if email has already received a CV
            for record in sent_emails.values():
                if record['email'] == email:
                    return f'📩 Vous avez déjà reçu un CV de type {record["cv_type"]}.'
                
            # Check if user has already received a CV
            if str(user_id) in sent_emails:
                previous_send = sent_emails[str(user_id)]
                if previous_send['cv_type'] == cv_type:
                    return f'📩 Vous avez déjà reçu un CV de type {cv_type}.'
                else:
                    return f'📩 Vous avez déjà reçu un CV de type {previous_send["cv_type"]}.'

        # Create and send email
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
        
        # Record sent email for non-admin users
        if not is_admin:
            sent_emails[str(user_id)] = {
                "email": email,
                "cv_type": cv_type,
                "sent_at": datetime.utcnow().isoformat()
            }
            save_sent_emails(sent_emails)
        
        return (
            f'✅ Le CV de type {cv_type.capitalize()} a été envoyé à {email}. ✉️\n\n'
            'سعداء جدا باهتمامكم بمبادرة CV_UP ! 🌟\n\n'
            'لقد تحصلتم على نسخة من مودال CV_UP التي ستساعدكم في تفادي أغلب الأخطاء التي قد تحرمكم من فرص العمل. 📝\n\n'
            'بقي الآن تعديلها وفقًا لمعلوماتكم. ✍️\n\n'
            '📄 ملاحظة: لا تنسوا دفع ثمن السيرة الذاتية إما بالتبرع بالدم في إحدى المستشفيات 🩸 أو التبرع بمبلغ من المال إلى جمعية البركة الجزائرية 💵، الذين بدورهم يوصلون التبرعات إلى غزة. 🙏\n\n'
            ' نرجو منكم تأكيد تسديد ثمن النسخة والذي كان التبرع بالدم في أحد المستشفيات أو التبرع لغزة عن طريق جمعية البركة. على الحساب   التالي CCP. 210 243 29 Clé 40 🏥✊'
        )
        
    except FileNotFoundError:
        logger.error(f"CV file not found for type: {cv_type}")
        return f'❌ Erreur: Le fichier CV de type {cv_type} n\'a pas été trouvé'
        
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email: {str(e)}")
        return f'❌ Erreur lors de l\'envoi de l\'e-mail: Problème de serveur SMTP'
        
    except Exception as e:
        logger.error(f"Unexpected error sending email: {str(e)}")
        return f'❌ Une erreur inattendue s\'est produite lors de l\'envoi de l\'e-mail'
