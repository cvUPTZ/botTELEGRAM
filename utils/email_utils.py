import smtplib
import logging
import json
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any
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

async def load_sent_emails() -> Dict[str, Any]:
    """Load the sent emails history from JSON file"""
    try:
        with open(SENT_EMAILS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"Error loading sent emails: {str(e)}")
        return {}

async def save_sent_emails(sent_emails: Dict[str, Any]) -> None:
    """Save the sent emails history to JSON file"""
    try:
        with open(SENT_EMAILS_FILE, 'w') as f:
            json.dump(sent_emails, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving sent emails: {str(e)}")

async def send_email_with_cv(email: str, cv_type: str, user_id: int) -> str:
    """
    Send CV via email and track the sending history
    
    Args:
        email (str): Recipient email address
        cv_type (str): Type of CV ('junior' or 'senior')
        user_id (int): Telegram user ID
        
    Returns:
        str: Success or error message
    """
    # Validate CV type
    if cv_type.lower() not in CV_FILES:
        return '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".'
    
    # Load sent emails history
    sent_emails = await load_sent_emails()
    
    # Check if user is admin
    is_admin = user_id in ADMIN_USER_IDS
    
    # Check previous sends for non-admin users
    if not is_admin:
        user_entry = sent_emails.get(email) or sent_emails.get(str(user_id))
        
        if user_entry:
            if user_entry['cv_type'] == cv_type:
                return f'📩 Vous avez déjà reçu un CV de type {cv_type}. Vous ne pouvez pas en demander un autre du même type.'
            else:
                return f'📩 Vous avez déjà reçu un CV de type {user_entry["cv_type"]}. Vous ne pouvez pas demander un CV de type différent.'

    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = f'{cv_type.capitalize()} CV'
        
        # Attach CV file
        part = MIMEBase('application', 'octet-stream')
        with open(CV_FILES[cv_type.lower()], 'rb') as file:
            part.set_payload(file.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={cv_type}_cv.docx')
        msg.attach(part)
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email, msg.as_string())
        
        # Update sent emails history for non-admin users
        if not is_admin:
            user_data = {
                'cv_type': cv_type,
                'email': email,
                'user_id': str(user_id)
            }
            sent_emails[email] = user_data
            sent_emails[str(user_id)] = user_data
            await save_sent_emails(sent_emails)
        
        # Return success message
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
