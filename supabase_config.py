# supabase_config.py

import os
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class SupabaseManager:
    def __init__(self):
        self.url: str = os.environ.get("SUPABASE_URL")
        self.key: str = os.environ.get("SUPABASE_KEY")
        if not self.url or not self.key:
            raise ValueError("Missing Supabase credentials in environment variables")
        self.client: Client = create_client(self.url, self.key)

    async def initialize_tables(self):
        """Initialize all required tables if they don't exist"""
        try:
            # SQL for creating tables
            create_tables_sql = """
            -- Create sent_emails table if it doesn't exist
            CREATE TABLE IF NOT EXISTS sent_emails (
                user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), -- Renamed from id to user_id
                user_id TEXT NOT NULL,
                email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'sent', -- Default value for status
                cv_type TEXT NOT NULL,
                sent_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()), -- Added sent_at column
                created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
            );

            -- Create questions table if it doesn't exist
            CREATE TABLE IF NOT EXISTS questions (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answered BOOLEAN DEFAULT FALSE,
                answer TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
            );

            -- Create linkedin_verifications table if it doesn't exist
            CREATE TABLE IF NOT EXISTS linkedin_verifications (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id TEXT NOT NULL,
                verification_code TEXT NOT NULL,
                verified BOOLEAN DEFAULT FALSE,
                verified_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
                UNIQUE(user_id)
            );
            """
            
            # Execute the SQL
            await self.client.sql(create_tables_sql)
            logger.info("Database tables initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing tables: {str(e)}")
            raise

    async def insert_sent_email(self, user_id: str, email: str, cv_type: str) -> Dict[str, Any]:
        """
        Insert a record of sent email
        
        Args:
            user_id (str): Telegram user ID
            email (str): Recipient email
            cv_type (str): Type of CV (junior/senior)
            
        Returns:
            Dict[str, Any]: Inserted record
        """
        try:
            data = {
                "user_id": user_id,
                "email": email,
                "status": "sent",  # Status is explicitly set here
                "cv_type": cv_type,
                "sent_at": datetime.utcnow().isoformat(),  # Set sent_at when inserting
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = await self.client.table('sent_emails').insert(data).execute()
            logger.info(f"Email record inserted for user {user_id}")
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Error inserting sent email: {str(e)}")
            raise

    async def get_user_sent_emails(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all emails sent to a specific user"""
        try:
            result = await self.client.table('sent_emails')\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"Error fetching sent emails: {str(e)}")
            raise

    async def insert_question(self, user_id: str, question: str) -> Dict[str, Any]:
        """Insert a new question"""
        try:
            data = {
                "user_id": user_id,
                "question": question,
                "answered": False,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = await self.client.table('questions').insert(data).execute()
            logger.info(f"Question inserted for user {user_id}")
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Error inserting question: {str(e)}")
            raise

    async def update_linkedin_verification(self, user_id: str, verified: bool = True) -> Dict[str, Any]:
        """Update LinkedIn verification status"""
        try:
            data = {
                "verified": verified,
                "verified_at": datetime.utcnow().isoformat() if verified else None
            }
            
            result = await self.client.table('linkedin_verifications')\
                .update(data)\
                .eq("user_id", user_id)\
                .execute()
                
            logger.info(f"LinkedIn verification updated for user {user_id}")
            return result.data[0]
            
        except Exception as e:
            logger.error(f"Error updating LinkedIn verification: {str(e)}")
            raise

    async def get_linkedin_verification(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get LinkedIn verification status for a user"""
        try:
            result = await self.client.table('linkedin_verifications')\
                .select("*")\
                .eq("user_id", user_id)\
                .single()\
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"Error fetching LinkedIn verification: {str(e)}")
            return None

# Initialize the Supabase manager
supabase_manager = SupabaseManager()

# Helper function to ensure tables exist
async def ensure_database_setup():
    """Ensure all required database tables exist"""
    try:
        await supabase_manager.initialize_tables()
        logger.info("Database setup completed successfully")
    except Exception as e:
        logger.error(f"Database setup failed: {str(e)}")
        raise
