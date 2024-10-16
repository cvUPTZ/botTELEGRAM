import json
import logging
from config import QUESTIONS_FILE, SENT_EMAILS_FILE, SCRAPED_DATA_FILE

logger = logging.getLogger(__name__)

def load_json_file(filename):
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        logger.warning(f"File not found: {filename}. Creating an empty file.")
        save_json_file(filename, {})
        return {}
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from file: {filename}")
        return {}

def save_json_file(filename, data):
    try:
        with open(filename, 'w') as file:
            json.dump(data, file, indent=4)
    except IOError as e:
        logger.error(f"Error writing to file {filename}: {str(e)}")

def load_questions():
    questions = load_json_file(QUESTIONS_FILE)
    next_id = max(map(int, questions.keys()), default=0) + 1
    return questions, next_id

def save_questions(questions):
    save_json_file(QUESTIONS_FILE, questions)

def load_sent_emails():
    return load_json_file(SENT_EMAILS_FILE)

def save_sent_emails(sent_emails):
    save_json_file(SENT_EMAILS_FILE, sent_emails)

def load_scraped_data():
    return load_json_file(SCRAPED_DATA_FILE)

def track_user(user_id, chat_id):
    # Implement user tracking logic here
    # For example, you could save this information to a database or a file
    logger.info(f"Tracked user {user_id} in chat {chat_id}")