import smtplib
from email.mime.multipart import MIMEMultipart
from telegram.ext import ContextTypes

from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any
from datetime import datetime
import logging
import motor.motor_asyncio
from config import (
    EMAIL_ADDRESS,
    EMAIL_PASSWORD,
    SMTP_SERVER,
    SMTP_PORT,
    CV_FILES,
    ADMIN_USER_IDS,
    MONGODB_URI
)

logger = logging.getLogger(__name__)

# Initialize MongoDB client
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = client.cvbot
sent_emails_collection = db.sent_emails

async def check_previous_sends(email: str, user_id: int):
    """Check if email or user has previously received a CV"""
    # Check if email has already received a CV
    email_record = await sent_emails_collection.find_one({"email": email})
    if email_record:
        return f'📩 Vous avez déjà reçu un CV de type {email_record["cv_type"]}.'
    
    # Check if user has already received a CV
    user_record = await sent_emails_collection.find_one({"user_id": str(user_id)})
    if user_record:
        return f'📩 Vous avez déjà reçu un CV de type {user_record["cv_type"]}.'
    
    return None

async def send_email_with_cv(email: str, cv_type: str, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Send CV via email and track sending history
    
    Args:
        email: Recipient email address
        cv_type: Type of CV (junior/senior)
        user_id: Telegram user ID
        context: Telegram context object containing bot instance
    
    Returns:
        str: Success or error message
    """
    if cv_type.lower() not in CV_FILES:
        return '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".'
    
    is_admin = user_id in ADMIN_USER_IDS
    
    try:
        # Check previous sends for non-admin users
        if not is_admin:
            previous_send = await check_previous_sends(email, user_id)
            if previous_send:
                return previous_send

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
            await sent_emails_collection.insert_one({
                "email": email,
                "cv_type": cv_type,
                "user_id": str(user_id),
                "sent_at": datetime.utcnow()
            })
        
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

# Example function to get statistics (optional)
async def get_sent_email_stats():
    """Get statistics about sent emails"""
    try:
        total_sent = await sent_emails_collection.count_documents({})
        junior_sent = await sent_emails_collection.count_documents({"cv_type": "junior"})
        senior_sent = await sent_emails_collection.count_documents({"cv_type": "senior"})
        
        return {
            "total_sent": total_sent,
            "junior_sent": junior_sent,
            "senior_sent": senior_sent
        }
    except Exception as e:
        logger.error(f"Error getting email stats: {str(e)}")
        return None
