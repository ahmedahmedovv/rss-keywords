from flask import Flask, render_template, request, jsonify, url_for
import json
from collections import Counter
from urllib.parse import urlencode, unquote
import re
from html import unescape
from datetime import datetime
import dateutil.parser
from math import ceil

app = Flask(__name__)

# Add max and min functions to Jinja2's global context
app.jinja_env.globals.update(max=max, min=min)

ARTICLES_PER_PAGE = 10  # Number of articles per page

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
                # Ensure read status exists
                if 'read' not in article:
                    article['read'] = False
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
    read_filter = request.args.get('read_filter', 'all')
    sort_order = request.args.get('sort', 'desc')
    page = request.args.get('page', 1, type=int)
    
    articles = load_articles()
    
    # First filter by keywords if any
    if selected_keywords:
        filtered_articles = [
            article for article in articles
            if all(kw in article.get('keywords', []) for kw in selected_keywords)
        ]
    else:
        filtered_articles = articles
    
    # Then filter by read status
    if read_filter == 'read':
        filtered_articles = [article for article in filtered_articles if article.get('read', False)]
    elif read_filter == 'unread':
        filtered_articles = [article for article in filtered_articles if not article.get('read', False)]
    
    # Sort articles by date
    def parse_date(date_str):
        try:
            return datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            try:
                return dateutil.parser.parse(date_str)
            except:
                return datetime.min
    
    # Sort using the parsed dates
    filtered_articles.sort(
        key=lambda x: parse_date(x.get('published', '')),
        reverse=(sort_order == 'desc')
    )
    
    # Calculate pagination
    total_articles = len(filtered_articles)
    total_pages = ceil(total_articles / ARTICLES_PER_PAGE)
    page = min(max(page, 1), total_pages)  # Ensure page is within valid range
    
    # Slice articles for current page
    start_idx = (page - 1) * ARTICLES_PER_PAGE
    end_idx = start_idx + ARTICLES_PER_PAGE
    paginated_articles = filtered_articles[start_idx:end_idx]
    
    keywords = get_filtered_keywords(articles, selected_keywords)
    
    return render_template('index.html',
                         articles=paginated_articles,
                         keywords=keywords,
                         selected_keywords=selected_keywords,
                         read_filter=read_filter,
                         sort_order=sort_order,
                         page=page,
                         total_pages=total_pages,
                         total_articles=total_articles,
                         ARTICLES_PER_PAGE=ARTICLES_PER_PAGE)

@app.template_filter('toggle_keyword_url')
def toggle_keyword_url(keyword, current_keywords):
    new_keywords = current_keywords.copy()
    if keyword in new_keywords:
        new_keywords.remove(keyword)
    else:
        new_keywords.append(keyword)
    
    # Preserve current filters
    read_filter = request.args.get('read_filter', 'all')
    sort_order = request.args.get('sort', 'desc')
    
    # Build query parameters
    params = []
    for k in new_keywords:
        params.append(('keyword', k))
    if read_filter != 'all':
        params.append(('read_filter', read_filter))
    if sort_order != 'desc':
        params.append(('sort', sort_order))
    
    if params:
        return f"/?{urlencode(params)}"
    return "/"

@app.route('/toggle-read/<path:article_id>')
def toggle_read(article_id):
    try:
        # Decode the URL-encoded article ID
        decoded_id = unquote(unquote(article_id))
        
        # Load articles from file
        with open('data/rss_feed.json', 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        # Find and toggle article read status
        article_found = False
        current_status = False
        
        for article in articles:
            if article['link'] == decoded_id:
                article['read'] = not article.get('read', False)
                current_status = article['read']
                article_found = True
                break
        
        if not article_found:
            print(f"Article not found: {decoded_id}")  # Debug print
            return jsonify({'success': False, 'error': 'Article not found'})
        
        # Save updated articles back to file
        with open('data/rss_feed.json', 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True, 
            'read': current_status
        })
    except Exception as e:
        print(f"Error in toggle_read: {e}")  # Debug print
        return jsonify({'success': False, 'error': str(e)})

@app.template_filter('format_date')
def format_date(date_string):
    """Convert any date format to DD/MM/YYYY"""
    try:
        # First try to parse as DD/MM/YYYY
        try:
            date = datetime.strptime(date_string, '%d/%m/%Y')
            return date_string  # Already in correct format
        except ValueError:
            # If that fails, try parsing with dateutil
            date = dateutil.parser.parse(date_string)
            return date.strftime('%d/%m/%Y')
    except Exception as e:
        print(f"Error parsing date {date_string}: {e}")
        return date_string

if __name__ == '__main__':
    app.run(debug=True) 