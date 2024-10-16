import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
PORT = int(os.getenv('PORT', 5000))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

CV_FILES = {
    'junior': os.getenv('JUNIOR_CV_FILE'),
    'senior': os.getenv('SENIOR_CV_FILE')
}
QUESTIONS_FILE = os.getenv('QUESTIONS_FILE')
SENT_EMAILS_FILE = os.getenv('SENT_EMAILS_FILE')
SCRAPED_DATA_FILE = os.getenv('SCRAPED_DATA_FILE')
admin_user_ids = [int(id.strip()) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id.strip()]
