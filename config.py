import os
from dotenv import load_dotenv
load_dotenv()

# Supabase table names
QUESTIONS_TABLE = 'questions'
SENT_EMAILS_TABLE = 'sent_emails'
SCRAPED_DATA_TABLE = 'scraped_data'
USERS_TABLE = 'users'

# Application settings
VERIFICATION_CODE_LENGTH = 6
TOKEN_EXPIRY_BUFFER_MINUTES = 5
API_TIMEOUT_SECONDS = 10

# LinkedIn Configuration
LINKEDIN_POST_URL="https://www.linkedin.com/feed/update/urn:li:activity:7253152926490144768/"
LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID')
LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
LINKEDIN_REDIRECT_URI = 'https://bot-telegram-pied.vercel.app/linkedin-callback'
LINKEDIN_ACCESS_TOKEN='AQWgUSGuYXze9sqybjosgZxBGaVrljmRSyn81rRk9R1TOoWSwax9bl-NykX2505CYmn2CeS9YrIQK_OPBZnoCd1AOziCMQVtsOJmA-5UFP9aMx2uLF3loyctN9FKl915lfI4AAsvqLT0ypuI1C_K0ht8K5FXhJC5uYCg1ivNRWqPfaaeZtWZS2gw1P3w1qgroTNoxEbw4es093W1t2RzBTDU54V-_y99MBoR39sIiMgFdIWdzwYNd8IW3RPpIbb-IWRNF14bheCBV8S_5tr_EBoRsuAj2eVMlDW4SJ-9j92z-uQl5ks9vGUszG9H1PUmKbm390OphzweK78Sun4sOSmoqRYheQ'
LINKEDIN_SCOPE = 'email, openid, profile, r_organization_admin, r_organization_social, rw_organization_admin, w_member_social, w_organization_social'
COMPANY_PAGE_ID = 105488010
LINKEDIN_POST_ID = "7254038723820949505"

# Redis Configuration
REDIS_URL = os.getenv('REDIS_URL')
REDIS_VERIFICATION_TTL = 3600  # 1 hour
REDIS_TOKEN_TTL = 3600  # 1 hour
REDIS_STATE_TTL = 600  # 10 minutes
REDIS_RETRY_TTL = 86400  # 24 hours
REDIS_MAX_RETRIES = 3

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 4000))

# Email Configuration
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))

# CV Configuration
CV_FILES = {
    'junior': os.getenv('JUNIOR_CV_FILE'),
    'senior': os.getenv('SENIOR_CV_FILE')
}

# File paths
QUESTIONS_FILE = 'data/questions.json'
SENT_EMAILS_FILE = 'data/sent_emails.json'
SCRAPED_DATA_FILE = 'data/scraped_data.json'

# Admin Configuration
ADMIN_USER_IDS = [int(id.strip()) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id.strip()]

# Validate configuration
if not all([BOT_TOKEN, WEBHOOK_URL, EMAIL_ADDRESS, EMAIL_PASSWORD, SMTP_SERVER, CV_FILES['junior'], CV_FILES['senior']]):
    raise ValueError("Missing required environment variables. Please check your .env file.")
