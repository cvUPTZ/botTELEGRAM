import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def check_questions_table():
    """Check if the questions table exists in Supabase."""
    try:
        result = supabase.table('questions').select('id').limit(1).execute()
        if result.data:
            print("Questions table already exists.")
        else:
            print("Questions table does not exist or is empty.")
    except Exception as e:
        print(f"Error checking the 'questions' table: {e}. Please ensure it's created manually in Supabase.")

def check_sent_emails_table():
    """Check if the sent_emails table exists in Supabase."""
    try:
        result = supabase.table('sent_emails').select('id').limit(1).execute()
        if result.data:
            print("Sent_emails table already exists.")
        else:
            print("Sent_emails table does not exist or is empty.")
    except Exception as e:
        print(f"Error checking the 'sent_emails' table: {e}. Please ensure it's created manually in Supabase.")

def insert_question(user_id, question_text):
    """Insert a question into the questions table."""
    try:
        result = supabase.table('questions').insert({
            "user_id": user_id,
            "question": question_text,
            "answered": False,
            "answer": None
        }).execute()
        print(f"Inserted question: {result.data}")
    except Exception as e:
        print(f"Error inserting question: {e}")

def insert_sent_email(email, status):
    """Insert a sent email record into the sent_emails table."""
    try:
        result = supabase.table('sent_emails').insert({
            "id": str(email),  # You can customize the 'id' field as needed
            "email": email,
            "status": status
        }).execute()
        print(f"Inserted sent email: {result.data}")
    except Exception as e:
        print(f"Error inserting sent email: {e}")

if __name__ == "__main__":
    # Check if the tables exist
    check_questions_table()
    check_sent_emails_table()

    # Example insertions (you can customize or remove this part)
    insert_question(user_id=123, question_text="What is Supabase?")
    insert_sent_email(email="example@example.com", status="sent")

    print("Table operations completed.")
