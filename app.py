from flask import Flask, render_template, request, jsonify, url_for
import json
from collections import Counter
from urllib.parse import urlencode, unquote
import re
from html import unescape
from datetime import datetime, timedelta
import dateutil.parser
from math import ceil
from supabase import create_client
import os
from dotenv import load_dotenv
import arrow
from dateparser import parse
from utils.logger import setup_logger

app = Flask(__name__)

# Add max and min functions to Jinja2's global context
app.jinja_env.globals.update(max=max, min=min)

ARTICLES_PER_PAGE = 10  # Number of articles per page

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create logger for this module
logger = setup_logger('web_app')

def clean_html(text):
    """Remove HTML tags and decode HTML entities"""
    # First decode HTML entities
    text = unescape(text)
    # Then remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    return text

def load_articles():
    try:
        # Query articles from Supabase
        response = supabase.table('articles').select('*').execute()
        articles = response.data
        
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
    # First filter to only unread articles
    filtered_articles = [article for article in articles if not article.get('read', False)]
    
    if selected_keywords:
        # Filter articles that contain ALL selected keywords (case-insensitive)
        filtered_articles = [
            article for article in filtered_articles
            if all(any(kw.lower() == k.lower() for k in article.get('keywords', [])) 
                  for kw in selected_keywords)
        ]
    
    # Count keywords in filtered articles
    keyword_counter = Counter()
    for article in filtered_articles:
        # Convert all keywords to lowercase when counting
        keywords = [k.lower() for k in article.get('keywords', [])]
        keyword_counter.update(keywords)
    return keyword_counter.most_common(100)

def parse_date(date_str):
    """Parse date string ensuring YYYY-MM-DD format"""
    try:
        # First try parsing as YYYY-MM-DD
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        try:
            # If that fails, try dateutil parser and convert to YYYY-MM-DD
            return dateutil.parser.parse(date_str)
        except:
            return datetime.min

def format_date(date_string):
    """Convert any date format to DD/MM/YYYY for display"""
    try:
        date = parse(date_string)
        if date:
            return arrow.get(date).format('DD/MM/YYYY')
        return date_string
    except Exception:
        return date_string

@app.route('/')
def index():
    selected_keywords = request.args.getlist('keyword')
    read_filter = request.args.get('read_filter', 'unread')
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
    
    # Get favorite keywords
    favorite_keywords = []
    try:
        response = supabase.table('favorite_keywords').select('keyword').execute()
        favorite_keywords = [item['keyword'] for item in response.data]
    except Exception as e:
        logger.error(f"Error fetching favorite keywords: {e}", exc_info=True)
    
    return render_template('index.html',
                         articles=paginated_articles,
                         keywords=keywords,
                         selected_keywords=selected_keywords,
                         favorite_keywords=favorite_keywords,
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
        
        # Get current article status
        response = supabase.table('articles').select('read').eq('link', decoded_id).execute()
        
        if not response.data:
            return jsonify({'success': False, 'error': 'Article not found'})
            
        current_status = not response.data[0]['read']
        
        # Update article read status
        supabase.table('articles').update({'read': current_status}).eq('link', decoded_id).execute()
        
        return jsonify({
            'success': True, 
            'read': current_status
        })
    except Exception as e:
        print(f"Error in toggle_read: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.template_filter('format_date')
def format_date_filter(date_string):
    """Format date for display"""
    try:
        date = parse(date_string)
        if date:
            formatted_date = arrow.get(date).format('YYYY-MM-DD')
            logger.debug(f"Date formatting: {date_string} -> {formatted_date}")
            return formatted_date
        logger.warning(f"Could not parse date: {date_string}")
        return date_string
    except Exception as e:
        logger.error(f"Error formatting date {date_string}: {e}", exc_info=True)
        return date_string

# Make sure the filter is registered
app.jinja_env.filters['format_date'] = format_date_filter

def analyze_dates():
    """Analyze all dates in the database for consistency"""
    try:
        articles = load_articles()
        inconsistencies = []
        
        for article in articles:
            published = article.get('published', '')
            try:
                # Try to parse as DD/MM/YYYY
                original_date = datetime.strptime(published, '%d/%m/%Y')
                parsed_date = parse_date(published)
                formatted_date = format_date(published)
                
                # Check if the dates are consistent
                if original_date != parsed_date or original_date.strftime('%d/%m/%Y') != formatted_date:
                    inconsistencies.append({
                        'title': article.get('title', ''),
                        'original': published,
                        'parsed': parsed_date.strftime('%d/%m/%Y'),
                        'formatted': formatted_date
                    })
            except ValueError as e:
                inconsistencies.append({
                    'title': article.get('title', ''),
                    'original': published,
                    'error': str(e)
                })
        
        if inconsistencies:
            print("\nDate inconsistencies found:")
            for inc in inconsistencies:
                print(f"\nArticle: {inc['title']}")
                print(f"Original date: {inc['original']}")
                if 'error' in inc:
                    print(f"Error: {inc['error']}")
                else:
                    print(f"Parsed date: {inc['parsed']}")
                    print(f"Formatted date: {inc['formatted']}")
        else:
            print("\nAll dates are consistent in DD/MM/YYYY format")
            
    except Exception as e:
        print(f"Error analyzing dates: {e}")

# Add this to your main route to run the analysis
@app.route('/analyze-dates')
def run_date_analysis():
    analyze_dates()
    return "Date analysis complete. Check server logs."

def fix_date_formats():
    """Fix any inconsistent date formats in the database"""
    try:
        articles = load_articles()
        fixed_count = 0
        
        for article in articles:
            published = article.get('published', '')
            try:
                # Parse the date and ensure YYYY-MM-DD format
                date = parse_date(published)
                correct_format = date.strftime('%Y-%m-%d')
                
                # Update if format is different
                if published != correct_format:
                    article['published'] = correct_format
                    fixed_count += 1
            except Exception as e:
                print(f"Error fixing date for article '{article.get('title', '')}': {e}")
        
        if fixed_count > 0:
            # Save the fixed articles back to the file
            with open('data/rss_feed.json', 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=2)
            print(f"\nFixed {fixed_count} date format inconsistencies")
        else:
            print("\nNo date formats needed fixing")
            
    except Exception as e:
        print(f"Error fixing dates: {e}")

@app.route('/fix-dates')
def run_date_fixes():
    fix_date_formats()
    return "Date fixes complete. Check server logs."

# Add this new route to handle favoriting keywords
@app.route('/toggle-favorite-keyword', methods=['POST'])
def toggle_favorite_keyword():
    try:
        data = request.get_json()
        keyword = data.get('keyword')
        
        if not keyword:
            return jsonify({'success': False, 'error': 'No keyword provided'})
            
        # Normalize keyword to lowercase
        keyword = keyword.lower()
            
        # Check if keyword is already favorited
        response = supabase.table('favorite_keywords').select('*').eq('keyword', keyword).execute()
        
        if response.data:
            # If exists, remove it
            supabase.table('favorite_keywords').delete().eq('keyword', keyword).execute()
            return jsonify({'success': True, 'status': 'removed'})
        else:
            # If doesn't exist, add it
            supabase.table('favorite_keywords').insert({'keyword': keyword}).execute()
            return jsonify({'success': True, 'status': 'added'})
            
    except Exception as e:
        logger.error(f"Error toggling favorite keyword: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)})

@app.template_filter('format_date_display')
def format_date_display_filter(date_string):
    """Format date for display in a user-friendly format"""
    try:
        date = parse(date_string)
        if date:
            # Store as YYYY-MM-DD but display as DD/MM/YYYY
            return arrow.get(date).format('DD/MM/YYYY')
        return date_string
    except Exception as e:
        logger.error(f"Error formatting display date {date_string}: {e}", exc_info=True)
        return date_string

def cleanup_old_articles():
    """Delete articles older than one month"""
    try:
        # Calculate the cutoff date (1 month ago)
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Delete articles older than cutoff_date
        response = supabase.table('articles').delete().lt('published', cutoff_date).execute()
        
        deleted_count = len(response.data) if response.data else 0
        logger.info(f"Deleted {deleted_count} articles older than {cutoff_date}")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up old articles: {e}", exc_info=True)
        return 0

# Add a route to manually trigger cleanup
@app.route('/cleanup')
def run_cleanup():
    count = cleanup_old_articles()
    return jsonify({
        'success': True,
        'deleted_count': count
    })

if __name__ == '__main__':
    app.run(debug=True) 