from rich.console import Console
from rich.progress import track
from deep_translator import GoogleTranslator
import feedparser
import json
import os
from datetime import datetime
import langdetect

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

def process_feed(url):
    """Process single RSS feed"""
    try:
        feed = feedparser.parse(url)
        articles = []
        
        for entry in track(feed.entries, description=f"Processing {url}..."):
            article = {
                'title': translate_if_needed(entry.title),
                'description': translate_if_needed(entry.description),
                'link': entry.link,
                'published': entry.get('published', ''),
                'original_language': detect_language(entry.title)
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
