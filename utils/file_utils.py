import logging
from supabase_config import supabase
from config import QUESTIONS_TABLE, SENT_EMAILS_TABLE, SCRAPED_DATA_TABLE, USERS_TABLE

logger = logging.getLogger(__name__)

def load_questions():
    try:
        response = supabase.table(QUESTIONS_TABLE).select('*').execute()
        questions = {str(item['id']): item for item in response.data}
        next_id = max(map(int, questions.keys()), default=0) + 1
        return questions, next_id
    except Exception as e:
        logger.error(f"Error loading questions from Supabase: {str(e)}")
        return {}, 1

def save_questions(questions):
    try:
        for question_id, question_data in questions.items():
            supabase.table(QUESTIONS_TABLE).upsert(question_data, on_conflict='id').execute()
    except Exception as e:
        logger.error(f"Error saving questions to Supabase: {str(e)}")

def load_sent_emails():
    try:
        response = supabase.table(SENT_EMAILS_TABLE).select('*').execute()
        return {str(item['id']): item for item in response.data}
    except Exception as e:
        logger.error(f"Error loading sent emails from Supabase: {str(e)}")
        return {}

def save_sent_emails(sent_emails):
    try:
        for email_id, email_data in sent_emails.items():
            supabase.table(SENT_EMAILS_TABLE).upsert(email_data, on_conflict='id').execute()
    except Exception as e:
        logger.error(f"Error saving sent emails to Supabase: {str(e)}")

def load_scraped_data():
    try:
        response = supabase.table(SCRAPED_DATA_TABLE).select('*').execute()
        return [item['data'] for item in response.data]
    except Exception as e:
        logger.error(f"Error loading scraped data from Supabase: {str(e)}")
        return []

def track_user(user_id, chat_id):
    try:
        supabase.table(USERS_TABLE).upsert({
            'user_id': user_id,
            'chat_id': chat_id,
            'last_active': 'now()'  # Supabase will replace this with the current timestamp
        }, on_conflict='user_id').execute()
        logger.info(f"Tracked user {user_id} in chat {chat_id}")
    except Exception as e:
        logger.error(f"Error tracking user in Supabase: {str(e)}")

# Helper functions for Supabase operations
def load_json_file(table_name):
    try:
        response = supabase.table(table_name).select('*').execute()
        return {str(item['id']): item for item in response.data}
    except Exception as e:
        logger.error(f"Error loading data from Supabase table {table_name}: {str(e)}")
        return {}

def save_json_file(table_name, data):
    try:
        supabase.table(table_name).upsert(data).execute()
    except Exception as e:
        logger.error(f"Error saving data to Supabase table {table_name}: {str(e)}")