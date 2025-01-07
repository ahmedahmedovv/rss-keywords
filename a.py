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

console = Console()

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
    """Clean text by removing punctuation, numbers, and extra whitespace"""
    text = text.lower()
    text = re.sub(r'[' + string.punctuation + ']', ' ', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
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
        
        # Extract keywords
        keywords = kw_extractor.extract_keywords(text)
        # Return only the keywords (not their scores)
        return [keyword for keyword, _ in keywords]
    except Exception as e:
        console.print(f"[red]Keyword extraction error: {e}[/red]")
        return []

def process_feed(url):
    """Process single RSS feed"""
    try:
        feed = feedparser.parse(url)
        articles = []
        
        for entry in track(feed.entries, description=f"Processing {url}..."):
            # Translate content first
            translated_title = translate_if_needed(entry.title)
            translated_description = translate_if_needed(entry.description)
            
            # Extract keywords from translated content
            title_keywords = extract_keywords(translated_title)
            desc_keywords = extract_keywords(translated_description)
            # Combine keywords and remove duplicates while preserving order
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

def main():
    # RSS feed URLs
    urls = [
        "https://notesfrompoland.com/feed/",
        "https://defence24.pl/_RSS"
    ]
    
    create_data_folder()
    
    # Process all feeds
    console.print("[green]Starting RSS feed processing...[/green]")
    all_articles = []
    
    for url in urls:
        console.print(f"\n[blue]Processing feed: {url}[/blue]")
        articles = process_feed(url)
        all_articles.extend(articles)
    
    # Save to JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"data/rss_feed_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    
    console.print(f"\n[green]Successfully saved {len(all_articles)} articles to {filename}[/green]")

if __name__ == "__main__":
    main()
