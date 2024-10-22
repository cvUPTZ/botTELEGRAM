import json
import redis
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from config import REDIS_URL
import time

redis_client = redis.from_url(REDIS_URL)

class LinkedInScraper:
    def __init__(self):
        self.options = webdriver.ChromeOptions()
        self.options.add_argument('--headless')  # Run in headless mode
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-gpu')
        # Add user agent to avoid detection
        self.options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    async def verify_linkedin_comment(self, user_id):
        """
        Verify if a user has commented on the LinkedIn post with their verification code
        """
        driver = None
        try:
            stored_code = redis_client.get(f"linkedin_verification_code:{user_id}")
            if not stored_code:
                print(f"No stored verification code found for user {user_id}")
                return False

            stored_code = stored_code.decode('utf-8') if isinstance(stored_code, bytes) else stored_code
            
            driver = webdriver.Chrome(options=self.options)
            post_url = "https://www.linkedin.com/posts/cv-updz_%D9%85%D9%88%D8%AF%D8%A7%D9%84-cv-%D9%88%D8%A7%D8%AC%D8%AF-activity-7254038723820949505-Tj12"
            
            # Load the page
            driver.get(post_url)
            time.sleep(3)  # Allow page to load initially

            # Wait for and click the comments button to expand comments
            try:
                comments_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='comments-button']"))
                )
                comments_button.click()
                time.sleep(2)  # Wait for comments to load
            except TimeoutException:
                print("Comments button not found")
                return False

            # Find all comments
            comments = driver.find_elements(By.CSS_SELECTOR, ".comments-comment-item__main-content .update-components-text span")
            
            print(f"Found {len(comments)} comments")
            
            # Check each comment for the verification code
            for comment in comments:
                comment_text = comment.text.strip()
                print(f"Checking comment: {comment_text}")
                if stored_code in comment_text:
                    print(f"Found matching verification code for user {user_id}")
                    return True

            print(f"No matching comment found for user {user_id}")
            return False

        except Exception as e:
            print(f"Error verifying LinkedIn comment: {str(e)}")
            return False
            
        finally:
            if driver:
                driver.quit()

    def is_linkedin_verified(self, user_id):
        """Check if a user has completed LinkedIn verification."""
        verified_data = redis_client.get(f"linkedin_verified:{user_id}")
        return bool(verified_data)

    def get_linkedin_profile(self, user_id):
        """Get the LinkedIn profile data for a verified user."""
        verified_data = redis_client.get(f"linkedin_verified:{user_id}")
        if verified_data:
            return json.loads(verified_data)
        return None
