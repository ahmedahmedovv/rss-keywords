from flask import Flask, render_template, request, jsonify, url_for
import json
from collections import Counter
from urllib.parse import urlencode, unquote
import re
from html import unescape
from math import ceil
from supabase import create_client
import os
from dotenv import load_dotenv
from utils.logger import setup_logger
from datetime import datetime, timedelta
import arrow
from dateparser import parse
from functools import wraps, lru_cache
import time
import cProfile
import io
import pstats
import yaml
from pathlib import Path

app = Flask(__name__)

# Add max and min functions to Jinja2's global context
app.jinja_env.globals.update(max=max, min=min)

ARTICLES_PER_PAGE = 10  # Number of articles per page

# Load environment variables
load_dotenv()

# Create logger for this module
logger = setup_logger('web_app')

# Add performance monitoring decorator
def performance_logger(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()
        
        duration = end_time - start_time
        logger.info(f"Function '{f.__name__}' took {duration:.2f} seconds to execute")
        
        return result
    return wrapper

# Add profiler decorator for detailed analysis
def profile_function(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not config['profiling']['enabled']:
            return f(*args, **kwargs)
            
        pr = cProfile.Profile()
        pr.enable()
        result = f(*args, **kwargs)
        pr.disable()
        
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats(config['profiling']['top_results'])
        logger.debug(f"Profile for {f.__name__}:\n{s.getvalue()}")
        
        return result
    return wrapper

def clean_html(text):
    """Remove HTML tags and decode HTML entities"""
    # First decode HTML entities
    text = unescape(text)
    # Then remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    return text

# Cache the articles for 5 minutes
@lru_cache(maxsize=1)
def get_cache_key():
    """Generate a cache key that changes based on configured cache duration"""
    now = datetime.now()
    cache_minutes = config['database']['cache_duration_minutes']
    return now.strftime('%Y-%m-%d-%H-%M-') + str(now.minute // cache_minutes)

# Load configuration
def load_config():
    config_path = Path(__file__).parent / 'config.yaml'
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Replace environment variables in config
        def replace_env_vars(config_dict):
            for key, value in config_dict.items():
                if isinstance(value, dict):
                    replace_env_vars(value)
                elif isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                    env_var = value[2:-1]
                    config_dict[key] = os.getenv(env_var)
        
        replace_env_vars(config)
        return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {
            'database': {
                'article_limit': 1000, 
                'cache_duration_minutes': 5,
                'supabase_url': os.getenv('SUPABASE_URL'),
                'supabase_key': os.getenv('SUPABASE_KEY')
            },
            'pagination': {'articles_per_page': 10},
            'cleanup': {'days_to_keep': 30},
            'caching': {
                'keywords_cache_minutes': 1,
                'articles_cache_minutes': 5
            },
            'profiling': {
                'enabled': True,
                'top_results': 20
            },
            'logging': {
                'level': 'INFO',
                'file_path': 'logs/app.log'
            },
            'server': {
                'host': '0.0.0.0',
                'port': 5000,
                'debug': False
            }
        }

# Load config at startup
config = load_config()

# Initialize Supabase client using config
supabase = create_client(
    config['database']['supabase_url'],
    config['database']['supabase_key']
)

@performance_logger
def load_articles():
    cache_key = get_cache_key()
    
    # Check if we have cached articles
    if hasattr(load_articles, 'cached_articles') and \
       hasattr(load_articles, 'cache_key') and \
       load_articles.cache_key == cache_key:
        logger.info("Returning cached articles")
        return load_articles.cached_articles
    
    try:
        # Query articles from Supabase with optimized select
        response = supabase.table('articles')\
            .select('link,title,description,keywords,read,created_at')\
            .order('created_at', desc=True)\
            .limit(config['database']['article_limit'])\
            .execute()
        articles = response.data
        
        # Process articles
        processed_articles = []
        for article in articles:
            processed_article = {
                'link': article['link'],
                'title': clean_html(article['title']),
                'description': clean_html(article['description']),
                'keywords': article.get('keywords', []),
                'read': article.get('read', False),
                'created_at': format_date_basic(article.get('created_at'))
            }
            processed_articles.append(processed_article)
        
        # Cache the results
        load_articles.cached_articles = processed_articles
        load_articles.cache_key = cache_key
        
        logger.info(f"Loaded {len(processed_articles)} articles in fresh query")
        return processed_articles
    except Exception as e:
        logger.error(f"Error loading articles: {e}", exc_info=True)
        return []

def format_date_basic(date_string):
    """Simple date formatting without complex parsing"""
    try:
        if not date_string:
            return None
        date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return date_obj.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return date_string

# Cache favorite keywords for 1 minute
@lru_cache(maxsize=1)
def get_favorite_keywords():
    try:
        response = supabase.table('favorite_keywords').select('keyword').execute()
        return [item['keyword'] for item in response.data]
    except Exception as e:
        logger.error(f"Error fetching favorite keywords: {e}", exc_info=True)
        return []

@performance_logger
@profile_function
def get_filtered_keywords(articles, selected_keywords=None, favorite_keywords=None):
    # First filter to only unread articles
    filtered_articles = [article for article in articles if not article.get('read', False)]
    
    if selected_keywords:
        # Filter articles that contain ALL selected keywords (case-insensitive)
        filtered_articles = [
            article for article in filtered_articles
            if all(any(kw.lower() == k.lower() for k in article.get('keywords', [])) 
                  for kw in selected_keywords)
        ]
    
    # Count ALL keywords in filtered articles
    keyword_counter = Counter()
    for article in filtered_articles:
        # Convert all keywords to lowercase when counting
        keywords = [k.lower() for k in article.get('keywords', [])]
        keyword_counter.update(keywords)
    
    # Get the most common keywords (excluding favorites)
    non_favorite_keywords = [
        (kw, count) for kw, count in keyword_counter.most_common()
        if not favorite_keywords or kw.lower() not in {f.lower() for f in favorite_keywords}
    ][:100]
    
    # Add all favorite keywords with their actual counts and sort by count
    favorite_keyword_counts = [
        (kw, keyword_counter[kw.lower()]) 
        for kw in (favorite_keywords or [])
    ]
    favorite_keyword_counts.sort(key=lambda x: (-x[1], x[0].lower()))  # Sort by count desc, then keyword asc
    
    # Combine favorite keywords and top non-favorite keywords
    return favorite_keyword_counts + non_favorite_keywords

@performance_logger
@profile_function
@app.route('/')
def index():
    start_time = time.time()
    
    selected_keywords = request.args.getlist('keyword')
    read_filter = request.args.get('read_filter', 'unread')
    page = request.args.get('page', 1, type=int)
    sort_order = request.args.get('sort', 'desc')
    
    # Load cached data
    articles = load_articles()
    favorite_keywords = get_favorite_keywords()
    
    # Filter articles (now working with cached data)
    filtered_articles = articles
    if selected_keywords:
        filtered_articles = [
            article for article in filtered_articles
            if all(kw in article.get('keywords', []) for kw in selected_keywords)
        ]
    
    if read_filter == 'read':
        filtered_articles = [article for article in filtered_articles if article.get('read', False)]
    elif read_filter == 'unread':
        filtered_articles = [article for article in filtered_articles if not article.get('read', False)]
    
    # Sort articles (they should already be sorted from the database)
    if sort_order == 'asc':
        filtered_articles.reverse()
    
    # Pagination
    total_articles = len(filtered_articles)
    total_pages = ceil(total_articles / config['pagination']['articles_per_page'])
    page = min(max(page, 1), total_pages)
    start_idx = (page - 1) * config['pagination']['articles_per_page']
    end_idx = start_idx + config['pagination']['articles_per_page']
    paginated_articles = filtered_articles[start_idx:end_idx]
    
    # Get keywords with caching
    keywords = get_filtered_keywords(articles, selected_keywords, favorite_keywords)
    
    end_time = time.time()
    logger.info(f"Index page rendered in {end_time - start_time:.2f} seconds")
    
    return render_template('index.html',
                         articles=paginated_articles,
                         keywords=keywords,
                         selected_keywords=selected_keywords,
                         favorite_keywords=favorite_keywords,
                         read_filter=read_filter,
                         page=page,
                         total_pages=total_pages,
                         total_articles=total_articles,
                         ARTICLES_PER_PAGE=ARTICLES_PER_PAGE,
                         sort_order=sort_order)

@app.template_filter('toggle_keyword_url')
def toggle_keyword_url(keyword, current_keywords):
    new_keywords = current_keywords.copy()
    if keyword in new_keywords:
        new_keywords.remove(keyword)
    else:
        new_keywords.append(keyword)
    
    # Preserve current filters and sort order
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
        if not date_string:
            return "Unknown date"
            
        date = parse(date_string)
        if date:
            # Get current time
            now = arrow.utcnow()
            # Convert to UTC to ensure consistent comparison
            article_date = arrow.get(date).to('UTC')
            
            # Calculate time difference
            diff = now - article_date
            hours_diff = diff.total_seconds() / 3600
            
            # Format based on how long ago the article was added
            if article_date.date() == now.date():
                if hours_diff < 1:
                    minutes = int(diff.total_seconds() / 60)
                    formatted_date = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                else:
                    hours = int(hours_diff)
                    formatted_date = f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif article_date.date() == now.shift(days=-1).date():
                formatted_date = "Yesterday"
            elif diff.days < 7:
                formatted_date = f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
            elif diff.days < 30:
                weeks = diff.days // 7
                formatted_date = f"{weeks} week{'s' if weeks != 1 else ''} ago"
            else:
                # For older articles, show the date
                formatted_date = article_date.format('MMM D, YYYY')
            
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

# Add a route to view performance metrics
@app.route('/performance')
def performance_metrics():
    try:
        # Get database stats
        start_time = time.time()
        articles_count = len(load_articles())
        db_time = time.time() - start_time
        
        # Get memory usage
        import psutil
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB
        
        return jsonify({
            'articles_count': articles_count,
            'database_query_time': f"{db_time:.2f}s",
            'memory_usage': f"{memory_usage:.2f}MB",
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(
        host=config['server']['host'],
        port=config['server']['port'],
        debug=config['server']['debug']
    ) 