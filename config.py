import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8443))

EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))

CV_FILES = {
    'junior': os.getenv('JUNIOR_CV_FILE'),
    'senior': os.getenv('SENIOR_CV_FILE')
}

QUESTIONS_FILE = 'data/questions.json'
SENT_EMAILS_FILE = 'data/sent_emails.json'
SCRAPED_DATA_FILE = 'data/scraped_data.json'

ADMIN_USER_IDS = [int(id.strip()) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id.strip()]