from supabase import create_client
import os
from dotenv import load_dotenv
from dateparser import parse
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import logging

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def convert_date_format(date_string):
    """Convert any date format to YYYY-MM-DD"""
    try:
        # Try RFC 2822 format first
        if ',' in date_string and any(day in date_string for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']):
            try:
                date_obj = parsedate_to_datetime(date_string)
                return date_obj.strftime('%Y-%m-%d')
            except Exception as e:
                logger.debug(f"Failed to parse RFC 2822 date: {e}")
        
        # Try regular date parsing
        date_obj = parse(date_string)
        if date_obj:
            return date_obj.strftime('%Y-%m-%d')
        
        logger.warning(f"Could not parse date: {date_string}")
        return None
        
    except Exception as e:
        logger.error(f"Error converting date format for {date_string}: {e}")
        return None

def migrate_dates():
    """Migrate all article dates to YYYY-MM-DD format"""
    try:
        # Get all articles
        response = supabase.table('articles').select('*').execute()
        articles = response.data
        
        updated_count = 0
        failed_count = 0
        
        logger.info(f"Starting migration of {len(articles)} articles")
        
        for article in articles:
            if 'published' in article:
                original_date = article['published']
                try:
                    new_date = convert_date_format(original_date)
                    if new_date and new_date != original_date:
                        # Update article with new date format
                        supabase.table('articles').update(
                            {'published': new_date}
                        ).eq('id', article['id']).execute()
                        updated_count += 1
                        logger.debug(f"Updated date format: {original_date} -> {new_date}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to update article {article.get('id')}: {e}")
        
        logger.info(f"""
Migration completed:
- Total articles processed: {len(articles)}
- Successfully updated: {updated_count}
- Failed to update: {failed_count}
""")
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")

def cleanup_old_articles():
    """Delete articles older than 30 days"""
    try:
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        logger.info(f"Cleaning up articles older than {cutoff_date}")
        
        # First check how many articles will be deleted
        check_response = supabase.table('articles').select('id').lt('published', cutoff_date).execute()
        to_delete_count = len(check_response.data) if check_response.data else 0
        
        if to_delete_count > 0:
            logger.info(f"Found {to_delete_count} articles to delete")
            # Proceed with deletion
            response = supabase.table('articles').delete().lt('published', cutoff_date).execute()
            deleted_count = len(response.data) if response.data else 0
            logger.info(f"Deleted {deleted_count} articles older than {cutoff_date}")
            return deleted_count
        else:
            logger.info("No old articles to delete")
            return 0
        
    except Exception as e:
        logger.error(f"Error cleaning up old articles: {e}")
        return 0

if __name__ == "__main__":
    logger.info("Starting date migration process")
    migrate_dates()
    cleanup_old_articles() 