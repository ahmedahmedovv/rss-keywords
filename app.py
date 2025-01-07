from flask import Flask, render_template, request
import json
from collections import Counter
from urllib.parse import urlencode
import re
from html import unescape

app = Flask(__name__)

def clean_html(text):
    """Remove HTML tags and decode HTML entities"""
    # First decode HTML entities
    text = unescape(text)
    # Then remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    return text

def load_articles():
    try:
        with open('data/rss_feed.json', 'r', encoding='utf-8') as f:
            articles = json.load(f)
            # Clean HTML from title and description
            for article in articles:
                article['title'] = clean_html(article['title'])
                article['description'] = clean_html(article['description'])
            return articles
    except Exception as e:
        print(f"Error loading articles: {e}")
        return []

def get_filtered_keywords(articles, selected_keywords=None):
    # Start with all articles if no keywords selected
    filtered_articles = articles
    if selected_keywords:
        # Filter articles that contain ALL selected keywords
        filtered_articles = [
            article for article in articles
            if all(kw in article.get('keywords', []) for kw in selected_keywords)
        ]
    
    # Count keywords in filtered articles
    keyword_counter = Counter()
    for article in filtered_articles:
        keyword_counter.update(article.get('keywords', []))
    return keyword_counter.most_common(100)

@app.route('/')
def index():
    selected_keywords = request.args.getlist('keyword')
    articles = load_articles()
    
    if selected_keywords:
        filtered_articles = [
            article for article in articles
            if all(kw in article.get('keywords', []) for kw in selected_keywords)
        ]
    else:
        filtered_articles = articles
    
    keywords = get_filtered_keywords(articles, selected_keywords)
    
    return render_template('index.html',
                         articles=filtered_articles,
                         keywords=keywords,
                         selected_keywords=selected_keywords)

@app.template_filter('toggle_keyword_url')
def toggle_keyword_url(keyword, current_keywords):
    new_keywords = current_keywords.copy()
    if keyword in new_keywords:
        new_keywords.remove(keyword)
    else:
        new_keywords.append(keyword)
    
    if new_keywords:
        return f"/?{urlencode([('keyword', k) for k in new_keywords])}"
    return "/"

if __name__ == '__main__':
    app.run(debug=True) 