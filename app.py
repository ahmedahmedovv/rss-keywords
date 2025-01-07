from flask import Flask, render_template
import json
from collections import Counter

app = Flask(__name__)

def load_articles():
    try:
        with open('data/rss_feed.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading articles: {e}")
        return []

def get_all_keywords():
    articles = load_articles()
    # Collect all keywords and their frequencies
    keyword_counter = Counter()
    for article in articles:
        keyword_counter.update(article.get('keywords', []))
    # Return top 50 keywords
    return keyword_counter.most_common(50)

@app.route('/')
def index():
    articles = load_articles()
    keywords = get_all_keywords()
    return render_template('index.html', articles=articles, keywords=keywords)

@app.route('/keyword/<keyword>')
def keyword_filter(keyword):
    articles = load_articles()
    filtered_articles = [
        article for article in articles 
        if keyword in article.get('keywords', [])
    ]
    keywords = get_all_keywords()
    return render_template('index.html', 
                         articles=filtered_articles, 
                         keywords=keywords, 
                         selected_keyword=keyword)

if __name__ == '__main__':
    app.run(debug=True) 