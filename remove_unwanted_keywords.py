from dotenv import load_dotenv
import os
from supabase.client import create_client
from rich.console import Console
from rich.progress import track

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

console = Console()

def remove_unwanted_keywords():
    """Remove unwanted keywords from existing articles in the database"""
    
    # Define unwanted keywords (same as in main script)
    unwanted_keywords = {'pln', 'pay', 'margin-bottom', 'display', 'height', 'monday', 'tuesday', 
                        'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 
                        'href', 'rel', 'months', 'vspace', 'image', 'alt', 'years', 
                        'head', 'class', 'time', 'jpeg', 'left', 'width', 'type', 
                        'year', 'month', 'day', 'hspace', 'src', 'img', 'align',
                        'january', 'february', 'march', 'april', 'may', 'june', 
                        'july', 'august', 'september', 'october', 'november', 'december'}
    
    try:
        # Fetch all articles
        response = supabase.table('articles').select('id', 'keywords').execute()
        articles = response.data
        
        console.print(f"[blue]Found {len(articles)} articles to process[/blue]")
        
        updated_count = 0
        for article in track(articles, description="Cleaning keywords..."):
            if not article.get('keywords'):
                continue
                
            # Filter out unwanted keywords
            cleaned_keywords = [
                keyword for keyword in article['keywords'] 
                if keyword.lower().strip() not in unwanted_keywords
            ]
            
            # Update article if keywords were removed
            if len(cleaned_keywords) != len(article['keywords']):
                supabase.table('articles')\
                    .update({'keywords': cleaned_keywords})\
                    .eq('id', article['id'])\
                    .execute()
                updated_count += 1
            
            # Add debug printing for a few articles
            if updated_count < 3:  # Only print first 3 for debugging
                console.print(f"Original keywords: {article['keywords']}")
                console.print(f"Cleaned keywords: {cleaned_keywords}")
                console.print("---")
        
        console.print(f"[green]Successfully cleaned keywords from {updated_count} articles[/green]")
        
    except Exception as e:
        console.print(f"[red]Error cleaning keywords: {e}[/red]")

if __name__ == "__main__":
    remove_unwanted_keywords() 