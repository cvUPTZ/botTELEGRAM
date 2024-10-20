from postgrest.exceptions import APIError
import json
from config import QUESTIONS_FILE, SENT_EMAILS_FILE, SCRAPED_DATA_FILE
from config import QUESTIONS_TABLE, SENT_EMAILS_TABLE, SCRAPED_DATA_TABLE
from utils.file_utils import check_supabase_connection

def migrate_json_to_supabase(file_path, table_name):
    with open(file_path, 'r') as file:
        data = json.load(file)
        for key, value in data.items():
            item = value if isinstance(value, dict) else {"email": key, "status": value}
            
            if table_name == QUESTIONS_TABLE:
                item['id'] = int(key)
            elif table_name == SENT_EMAILS_TABLE:
                item['id'] = key  # Use email as id for sent_emails table
            
            print(f"Attempting to insert/upsert: {item}")
            try:
                result = supabase.table(table_name).upsert(item).execute()
                print(f"Upserted: {result}")
            except APIError as e:
                print(f"Upsert failed. Error: {str(e)}")
                print(f"Problematic item: {item}")
            except Exception as e:
                print(f"An unexpected error occurred: {str(e)}")
                print(f"Problematic item: {item}")
    print(f"Finished processing data from {file_path} to {table_name} table in Supabase")

if __name__ == "__main__":
    check_supabase_connection()  # Check connection before proceeding
    migrate_json_to_supabase(QUESTIONS_FILE, QUESTIONS_TABLE)
    migrate_json_to_supabase(SENT_EMAILS_FILE, SENT_EMAILS_TABLE)
    
    # For scraped data, assuming it's a list in the JSON file
    # with open(SCRAPED_DATA_FILE, 'r') as file:
    #     scraped_data = json.load(file)
    # for item in scraped_data:
    #     supabase.table(SCRAPED_DATA_TABLE).insert({'data': item}).execute()
    
    # print(f"Migrated scraped data from {SCRAPED_DATA_FILE} to {SCRAPED_DATA_TABLE} table in Supabase")

    print("Migration completed successfully")