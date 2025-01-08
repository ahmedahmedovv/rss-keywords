from supabase import create_client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

def migrate_keywords():
    try:
        # Get all articles
        response = supabase.table('articles').select('*').execute()
        articles = response.data
        
        # Update keywords to lowercase
        for article in articles:
            if 'keywords' in article:
                # Convert keywords to lowercase and remove duplicates
                keywords = list(set(k.lower() for k in article['keywords']))
                # Update article
                supabase.table('articles').update({'keywords': keywords}).eq('id', article['id']).execute()
        
        # Get all favorite keywords
        response = supabase.table('favorite_keywords').select('*').execute()
        favorites = response.data
        
        # Update favorite keywords to lowercase
        seen = set()
        for favorite in favorites:
            keyword = favorite['keyword'].lower()
            if keyword in seen:
                # Delete duplicate
                supabase.table('favorite_keywords').delete().eq('id', favorite['id']).execute()
            else:
                # Update to lowercase
                supabase.table('favorite_keywords').update({'keyword': keyword}).eq('id', favorite['id']).execute()
                seen.add(keyword)
                
        print("Migration completed successfully")
        
    except Exception as e:
        print(f"Error during migration: {e}")

if __name__ == "__main__":
    migrate_keywords() 