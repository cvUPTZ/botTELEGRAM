import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any
from datetime import datetime
from config import (
    EMAIL_ADDRESS,
    EMAIL_PASSWORD,
    SMTP_SERVER,
    SMTP_PORT,
    CV_FILES,
    ADMIN_USER_IDS,
    SENT_EMAILS_TABLE
)

logger = logging.getLogger(__name__)

async def check_sent_email(supabase, email: str, user_id: str) -> Dict[str, Any]:
    """
    Check if email has been sent before using Supabase
    
    Args:
        supabase: Supabase client
        email (str): Email to check
        user_id (str): User ID to check
        
    Returns:
        Dict: Previous sent email entry if found, None otherwise
    """
    try:
        # Check by email
        response = await supabase.table(SENT_EMAILS_TABLE)\
            .select('*')\
            .or_(f'email.eq.{email},user_id.eq.{user_id}')\
            .execute()
        
        if response.data:
            return response.data[0]
        return None
        
    except Exception as e:
        logger.error(f"Error checking sent email in Supabase: {str(e)}")
        raise

async def record_sent_email(supabase, email: str, cv_type: str, user_id: str) -> None:
    """
    Record sent email in Supabase
    
    Args:
        supabase: Supabase client
        email (str): Recipient email
        cv_type (str): Type of CV sent
        user_id (str): User ID
    """
    try:
        await supabase.table(SENT_EMAILS_TABLE).insert({
            "email": email,
            "cv_type": cv_type,
            "user_id": user_id,
            "sent_at": datetime.utcnow().isoformat(),
        }).execute()
        
    except Exception as e:
        logger.error(f"Error recording sent email in Supabase: {str(e)}")
        raise

async def send_email_with_cv(email: str, cv_type: str, user_id: int, supabase) -> str:
    """
    Send CV via email and track the sending history in Supabase
    
    Args:
        email (str): Recipient email address
        cv_type (str): Type of CV ('junior' or 'senior')
        user_id (int): Telegram user ID
        supabase: Supabase client
        
    Returns:
        str: Success or error message
    """
    # Validate CV type
    if cv_type.lower() not in CV_FILES:
        return '❌ Type de CV incorrect. Veuillez utiliser "junior" ou "senior".'
    
    # Check if user is admin
    is_admin = user_id in ADMIN_USER_IDS
    
    try:
        # Check previous sends for non-admin users
        if not is_admin:
            previous_send = await check_sent_email(supabase, email, str(user_id))
            
            if previous_send:
                if previous_send['cv_type'] == cv_type:
                    return f'📩 Vous avez déjà reçu un CV de type {cv_type}. Vous ne pouvez pas en demander un autre du même type.'
                else:
                    return f'📩 Vous avez déjà reçu un CV de type {previous_send["cv_type"]}. Vous ne pouvez pas demander un CV de type différent.'

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
        
        # Record sent email for non-admin users
        if not is_admin:
            await record_sent_email(supabase, email, cv_type, str(user_id))
        
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
