from rich.console import Console
from rich.progress import track
from deep_translator import GoogleTranslator
import feedparser
import json
import os
from datetime import datetime, timedelta
import langdetect
from collections import Counter
import re
import string
import yake
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from bs4 import BeautifulSoup
import dateutil.parser
from supabase.client import create_client
from dotenv import load_dotenv
import arrow
from dateparser import parse
from utils.logger import setup_logger
from email.utils import parsedate_to_datetime

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

console = Console()

# Create logger for this module
logger = setup_logger('rss_processor')

# Download required NLTK data (run once)
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')

def create_data_folder():
    """Create data folder if it doesn't exist"""
    if not os.path.exists('data'):
        os.makedirs('data')

def detect_language(text):
    """Detect language of text, return 'en' if detection fails"""
    try:
        return langdetect.detect(text)
    except:
        return 'en'

def translate_if_needed(text):
    """Translate text to English if it's not already in English"""
    try:
        lang = detect_language(text)
        if lang != 'en':
            console.print(f"[yellow]Translating from {lang}...[/yellow]")
            return GoogleTranslator(source=lang, target='en').translate(text)
        return text
    except Exception as e:
        console.print(f"[red]Translation error: {e}[/red]")
        return text

def clean_text(text):
    """Clean text using NLTK for better text preprocessing"""
    try:
        # Remove HTML tags using BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text()
        
        # Tokenize
        tokens = word_tokenize(text.lower())
        
        # Initialize lemmatizer
        lemmatizer = WordNetLemmatizer()
        
        # Get English stop words
        stop_words = set(stopwords.words('english'))
        
        # Clean and lemmatize tokens
        cleaned_tokens = [
            lemmatizer.lemmatize(token) 
            for token in tokens 
            if token.isalnum() and  # Keep only alphanumeric
            token not in stop_words and  # Remove stop words
            len(token) > 2  # Remove short tokens
        ]
        
        # Join tokens back into text
        return ' '.join(cleaned_tokens)
    except Exception as e:
        print(f"Error cleaning text: {e}")
        return text

def extract_keywords(text):
    """Extract keywords from text using YAKE"""
    try:
        # Initialize YAKE keyword extractor
        kw_extractor = yake.KeywordExtractor(
            lan="en",              
            n=1,                   
            dedupLim=0.9,          
            dedupFunc='seqm',      
            windowsSize=1,         
            top=20,                
            features=None
        )
        
        # Unwanted keywords to filter out
        unwanted_keywords = {'pln', 'pay', 'margin-bottom', 'display', 'height', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'href', 'rel', 'months', 'vspace', 'image', 'alt', 'years', 'head', 'class', 'time', 'jpeg', 'left', 'width', 'type', 'year', 'month', 'day', 'hspace', 'src', 'img', 'align', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'}
        
        # Extract keywords
        keywords = kw_extractor.extract_keywords(text)
        # Filter out unwanted keywords and normalize case
        filtered_keywords = [
            keyword.lower() for keyword, _ in keywords 
            if keyword.lower() not in unwanted_keywords
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        filtered_keywords = [x for x in filtered_keywords if not (x in seen or seen.add(x))]
        
        return filtered_keywords
    except Exception as e:
        console.print(f"[red]Keyword extraction error: {e}[/red]")
        return []

def load_processed_urls():
    """Load all previously processed article URLs from Supabase"""
    processed_urls = set()
    try:
        # Query all article links from Supabase
        response = supabase.table('articles').select('link').execute()
        processed_urls.update(article['link'] for article in response.data)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch processed URLs: {e}[/yellow]")
    return processed_urls

def load_existing_articles():
    """Load existing articles from Supabase"""
    try:
        response = supabase.table('articles').select('*').execute()
        return response.data
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load existing articles: {e}[/yellow]")
    return []

def standardize_date(date_str):
    """Convert various date formats to DD/MM/YYYY format"""
    try:
        date = parse(date_str)
        if date:
            return arrow.get(date).format('DD/MM/YYYY')
        return date_str
    except Exception:
        return date_str

def format_date(date_string):
    """Convert any date format to DD/MM/YYYY"""
    try:
        date = parse(date_string)
        if date:
            return arrow.get(date).format('DD/MM/YYYY')
        return date_string
    except Exception:
        return date_string

def normalize_date(date_string):
    """Convert any date format to YYYY-MM-DD format for database storage"""
    try:
        # Handle RFC 2822 format (e.g. "Wed, 08 Jan 2025 17:57:38 -0000")
        if ',' in date_string and any(day in date_string for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']):
            try:
                date_obj = parsedate_to_datetime(date_string)
                return date_obj.strftime('%Y-%m-%d')
            except Exception as e:
                logger.debug(f"Failed to parse RFC 2822 date: {e}")
                # Continue with regular parsing if RFC 2822 parsing fails
        
        # Regular date parsing
        date = parse(date_string)
        if date:
            result = arrow.get(date).format('YYYY-MM-DD')
            logger.debug(f"Date conversion successful: {date_string} -> {result}")
            return result
        else:
            logger.warning(f"Could not parse date: {date_string}")
            return arrow.utcnow().format('YYYY-MM-DD')
    except Exception as e:
        logger.error(f"Error parsing date {date_string}: {e}", exc_info=True)
        return arrow.utcnow().format('YYYY-MM-DD')

def process_feed(url, processed_urls):
    """Process a single RSS feed"""
    try:
        feed = feedparser.parse(url)
        new_articles = []
        
        existing_articles = {}  # Initialize empty dict for existing articles
        
        for entry in feed.entries:
            try:
                # Skip if already processed
                if entry.link in processed_urls:
                    continue
                    
                # Get publication date
                if hasattr(entry, 'published'):
                    published = entry.published
                elif hasattr(entry, 'updated'):
                    published = entry.updated
                else:
                    published = datetime.now().strftime('%Y-%m-%d')
                
                # Normalize the date format
                published = normalize_date(published)

                # Process new article
                translated_title = translate_if_needed(entry.title)
                translated_description = translate_if_needed(entry.description)
                
                title_keywords = extract_keywords(translated_title)
                desc_keywords = extract_keywords(translated_description)
                combined_keywords = list(dict.fromkeys(title_keywords + desc_keywords))
                
                article = {
                    'title': translated_title,
                    'description': translated_description,
                    'link': entry.link,
                    'published': published,
                    'original_language': detect_language(entry.title),
                    'keywords': combined_keywords,
                    'read': existing_articles.get(entry.link, False)
                }
                new_articles.append(article)
            except Exception as e:
                console.print(f"[red]Error processing entry {entry.link}: {e}[/red]")
                continue
        
        return new_articles
    except Exception as e:
        console.print(f"[red]Error processing feed {url}: {e}[/red]")
        return []

def load_urls_from_file():
    """Load URLs from url.md file"""
    try:
        with open('url.md', 'r', encoding='utf-8') as f:
            # Read lines and remove empty ones
            urls = [line.strip() for line in f if line.strip()]
            console.print(f"[green]Loaded {len(urls)} URLs from url.md[/green]")
            return urls
    except Exception as e:
        console.print(f"[red]Error loading URLs from url.md: {e}[/red]")
        return []

def save_articles(articles):
    """Save articles to Supabase"""
    try:
        logger.info(f"Starting to save {len(articles)} articles")
        
        # Run cleanup before saving new articles
        try:
            # Calculate the cutoff date (1 month ago)
            cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            # Delete articles older than cutoff_date
            response = supabase.table('articles').delete().lt('published', cutoff_date).execute()
            deleted_count = len(response.data) if response.data else 0
            logger.info(f"Cleaned up {deleted_count} old articles (older than {cutoff_date})")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
        
        for article in articles:
            try:
                # Check if article already exists
                existing = supabase.table('articles').select('id').eq('link', article['link']).execute()
                
                if not existing.data:
                    logger.debug(f"Saving new article: {article['title']}")
                    
                    # Ensure date is in YYYY-MM-DD format
                    if 'published' in article:
                        try:
                            # Parse any date format and convert to YYYY-MM-DD
                            date_obj = parse(article['published'])
                            article['published'] = date_obj.strftime('%Y-%m-%d')
                        except Exception as e:
                            logger.error(f"Error converting date format for {article['title']}: {e}")
                            continue

                    supabase.table('articles').insert({
                        'title': article['title'],
                        'description': article['description'],
                        'link': article['link'],
                        'published': article['published'],
                        'original_language': article['original_language'],
                        'keywords': article['keywords'],
                        'read': article.get('read', False)
                    }).execute()
                else:
                    logger.debug(f"Article already exists: {article['title']}")
            except Exception as e:
                logger.error(f"Error saving article {article.get('title', 'Unknown')}: {e}", exc_info=True)
                continue
                
        logger.info("Successfully saved all articles")
        return True
        
    except Exception as e:
        logger.error("Error in save_articles function", exc_info=True)
        return False

def standardize_existing_dates():
    """Convert all existing dates to DD/MM/YYYY format"""
    try:
        if not os.path.exists('data/rss_feed.json'):
            return
            
        with open('data/rss_feed.json', 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        # Convert all dates to DD/MM/YYYY format
        for article in articles:
            if 'published' in article and article['published']:
                article['published'] = format_date(article['published'])
        
        # Save the updated articles
        with open('data/rss_feed.json', 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
            
        console.print("[green]Successfully standardized all dates to DD/MM/YYYY format[/green]")
    except Exception as e:
        console.print(f"[red]Error standardizing dates: {e}[/red]")

def delete_old_articles():
    """Delete articles older than one month"""
    try:
        # Calculate cutoff date (1 month ago)
        cutoff_date = arrow.utcnow().shift(months=-1)
        cutoff_date_str = cutoff_date.format('YYYY-MM-DD')
        
        # Delete old articles from Supabase
        response = supabase.table('articles').delete().lt('published', cutoff_date_str).execute()
        
        deleted_count = len(response.data)
        if deleted_count > 0:
            console.print(f"[green]Deleted {deleted_count} articles older than 30 days[/green]")
            
            # Get info about remaining articles
            remaining = supabase.table('articles').select('published').order('published').execute()
            if remaining.data:
                dates = [arrow.get(article['published']) for article in remaining.data]
                oldest = min(dates).format('DD/MM/YYYY')
                newest = max(dates).format('DD/MM/YYYY')
                console.print(f"[blue]Oldest retained article: {oldest}[/blue]")
                console.print(f"[blue]Newest retained article: {newest}[/blue]")
        else:
            console.print("[blue]No articles older than 30 days found[/blue]")
            
    except Exception as e:
        console.print(f"[red]Error deleting old articles: {e}[/red]")

def main():
    try:
        console.print("[blue]Starting cleanup of old articles...[/blue]")
        delete_old_articles()
        
        # Load URLs from file
        urls = load_urls_from_file()
        
        if not urls:
            console.print("[red]No URLs found in url.md. Exiting...[/red]")
            return
        
        # Process all feeds
        console.print("[green]Starting RSS feed processing...[/green]")
        total_new_articles = 0
        processed_urls = load_processed_urls()
        
        for url in urls:
            console.print(f"\n[blue]Processing feed: {url}[/blue]")
            new_articles = process_feed(url, processed_urls)
            
            if new_articles:
                # Save articles to Supabase
                save_articles(new_articles)
                total_new_articles += len(new_articles)
                console.print(f"[green]Saved {len(new_articles)} new articles from {url}[/green]")
                processed_urls.update(article['link'] for article in new_articles)
        
        if total_new_articles > 0:
            console.print(f"\n[green]Successfully processed all feeds[/green]")
            console.print(f"[green]Total new articles: {total_new_articles}[/green]")
            
            # Get total count from Supabase
            count = supabase.table('articles').select('id', count='exact').execute()
            console.print(f"[green]Total articles in database: {count.count}[/green]")
        else:
            console.print("[yellow]No new articles found[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error in main: {e}[/red]")

if __name__ == "__main__":
    main()
