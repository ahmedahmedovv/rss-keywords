from supabase import create_client
import os
from dotenv import load_dotenv
from dateparser import parse
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

def migrate_dates():
    try:
        # Get all articles
        response = supabase.table('articles').select('*').execute()
        articles = response.data
        
        updated_count = 0
        for article in articles:
            if 'published' in article:
                try:
                    # Parse the existing date
                    date_obj = parse(article['published'])
                    if date_obj:
                        # Convert to YYYY-MM-DD
                        new_date = date_obj.strftime('%Y-%m-%d')
                        if new_date != article['published']:
                            # Update article
                            supabase.table('articles').update(
                                {'published': new_date}
                            ).eq('id', article['id']).execute()
                            updated_count += 1
                except Exception as e:
                    print(f"Error processing date for article {article.get('id')}: {e}")
                    
        print(f"Successfully updated {updated_count} dates to YYYY-MM-DD format")
        
    except Exception as e:
        print(f"Error during date migration: {e}")

if __name__ == "__main__":
    migrate_dates() 