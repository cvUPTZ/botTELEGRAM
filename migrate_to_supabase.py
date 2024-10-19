import json
from supabase_config import supabase
from config import QUESTIONS_FILE, SENT_EMAILS_FILE, SCRAPED_DATA_FILE
from config import QUESTIONS_TABLE, SENT_EMAILS_TABLE, SCRAPED_DATA_TABLE

def migrate_json_to_supabase(file_path, table_name):
    with open(file_path, 'r') as file:
        data = json.load(file)
    
    for item in data.values():
        supabase.table(table_name).upsert(item).execute()

    print(f"Migrated data from {file_path} to {table_name} table in Supabase")

if __name__ == "__main__":
    migrate_json_to_supabase(QUESTIONS_FILE, QUESTIONS_TABLE)
    migrate_json_to_supabase(SENT_EMAILS_FILE, SENT_EMAILS_TABLE)
    
    # For scraped data, assuming it's a list in the JSON file
    with open(SCRAPED_DATA_FILE, 'r') as file:
        scraped_data = json.load(file)
    for item in scraped_data:
        supabase.table(SCRAPED_DATA_TABLE).insert({'data': item}).execute()
    
    print(f"Migrated scraped data from {SCRAPED_DATA_FILE} to {SCRAPED_DATA_TABLE} table in Supabase")

    print("Migration completed successfully")