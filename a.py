from rich.console import Console
from rich.progress import track
from deep_translator import GoogleTranslator
import feedparser
import json
import os
from datetime import datetime
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

console = Console()

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
            lan="en",              # language
            n=1,                   # extract single words
            dedupLim=0.9,          # deduplication threshold
            dedupFunc='seqm',      # deduplication function
            windowsSize=1,         # window size
            top=20,                # number of keywords to extract
            features=None
        )
        
        # Unwanted keywords to filter out
        unwanted_keywords = {'alt', 'years', 'head', 'class', 'time', 'jpeg', 'left', 'width', 'type', 'year', 'month', 'day', 'hspace', 'src', 'img', 'align', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'}
        
        # Extract keywords
        keywords = kw_extractor.extract_keywords(text)
        # Filter out unwanted keywords and return only the keywords (not their scores)
        filtered_keywords = [
            keyword for keyword, _ in keywords 
            if keyword.lower() not in unwanted_keywords
        ]
        
        return filtered_keywords
    except Exception as e:
        console.print(f"[red]Keyword extraction error: {e}[/red]")
        return []

def load_processed_urls():
    """Load all previously processed article URLs from the JSON file"""
    processed_urls = set()
    json_file = 'data/rss_feed.json'
    
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                processed_urls.update(article['link'] for article in data)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read {json_file}: {e}[/yellow]")
    return processed_urls

def load_existing_articles():
    """Load existing articles from the JSON file"""
    json_file = 'data/rss_feed.json'
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read {json_file}: {e}[/yellow]")
    return []

def process_feed(url, processed_urls):
    """Process single RSS feed, skipping already processed articles"""
    try:
        feed = feedparser.parse(url)
        articles = []
        
        for entry in track(feed.entries, description=f"Processing {url}..."):
            # Skip if article already processed
            if entry.link in processed_urls:
                console.print(f"[blue]Skipping already processed article: {entry.link}[/blue]")
                continue
                
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
                'published': entry.get('published', ''),
                'original_language': detect_language(entry.title),
                'keywords': combined_keywords
            }
            articles.append(article)
        
        return articles
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

def save_articles(articles, json_file):
    """Save articles to JSON file"""
    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        console.print(f"[red]Error saving articles: {e}[/red]")
        return False

def main():
    # Load URLs from file instead of hardcoding
    urls = load_urls_from_file()
    
    if not urls:
        console.print("[red]No URLs found in url.md. Exiting...[/red]")
        return
    
    create_data_folder()
    json_file = 'data/rss_feed.json'
    
    # Load previously processed URLs and existing articles
    processed_urls = load_processed_urls()
    all_articles = load_existing_articles()
    console.print(f"[green]Found {len(processed_urls)} previously processed articles[/green]")
    
    # Process all feeds
    console.print("[green]Starting RSS feed processing...[/green]")
    total_new_articles = 0
    
    for url in urls:
        console.print(f"\n[blue]Processing feed: {url}[/blue]")
        new_articles = process_feed(url, processed_urls)
        
        if new_articles:
            # Update the main articles list
            all_articles.extend(new_articles)
            total_new_articles += len(new_articles)
            
            # Save incrementally after each feed
            if save_articles(all_articles, json_file):
                console.print(f"[green]Saved {len(new_articles)} new articles from {url}[/green]")
                # Update processed URLs
                processed_urls.update(article['link'] for article in new_articles)
            else:
                console.print(f"[red]Failed to save articles from {url}[/red]")
    
    if total_new_articles > 0:
        console.print(f"\n[green]Successfully processed all feeds[/green]")
        console.print(f"[green]Total new articles: {total_new_articles}[/green]")
        console.print(f"[green]Total articles in database: {len(all_articles)}[/green]")
    else:
        console.print("[yellow]No new articles found[/yellow]")

if __name__ == "__main__":
    main()
