from flask import Flask, render_template, request, jsonify
import requests
import os
import sqlite3
import threading
import time
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from queue import Queue
import hashlib
import logging

load_dotenv()

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add thread status tracking
class NewsCollectorThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_run = None
        self.is_running = False
        self.status = "initialized"
        self.current_category = None
        self.current_keyword = None
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def get_status(self):
        return {
            "is_running": self.is_running,
            "status": self.status,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "current_category": self.current_category,
            "current_keyword": self.current_keyword
        }

# Add database lock
db_lock = threading.Lock()

# Naver API credentials
NAVER_CLIENT_ID = os.getenv('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.getenv('NAVER_CLIENT_SECRET')

# Search categories and keywords
SEARCH_CATEGORIES = {
    "전체": [],  # This will be populated with all keywords
    "데이터베이스_AI기술": ["MCP", "AI 데이터베이스", "인공지능 데이터베이스", "자율운영 데이터베이스"],
    "데이터베이스_일반": ["Oracle Database", "MySQL", "PostgreSQL", "MongoDB", "Redis"],
    "국내_경쟁_기업": ["네이버 클라우드", "카카오 클라우드", "KT 클라우드"],
    "해외_경쟁_기업": ["AWS", "Google Cloud", "Microsoft Azure", "IBM Cloud"],
    "오픈소스_직접_경쟁": ["PostgreSQL", "MySQL", "MariaDB", "MongoDB"],
    "유관_경쟁_기업": ["Snowflake", "Databricks"],
    "클라우드": ["클라우드 데이터베이스", "Cloud Database", "Database as a Service"],
    "AI": ["AI 데이터베이스", "인공지능 데이터베이스", "AI Database"]
}

# Populate "전체" category with all unique keywords
all_keywords = set()
for category, keywords in list(SEARCH_CATEGORIES.items())[1:]:  # Skip "전체" itself
    all_keywords.update(keywords)
SEARCH_CATEGORIES["전체"] = list(all_keywords)

# Queue for real-time updates
update_queue = Queue()

# Global variables for tracking news counts
category_news_counts = {category: 0 for category in SEARCH_CATEGORIES.keys()}
news_counts_lock = threading.Lock()

# Global variables
collector_thread = None

def init_db():
    with db_lock:
        conn = sqlite3.connect('news.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS news
                     (id TEXT PRIMARY KEY,
                      keyword TEXT,
                      title TEXT,
                      description TEXT,
                      link TEXT,
                      pub_date TEXT,
                      category TEXT,
                      created_at TEXT)''')
        conn.commit()
        conn.close()

def update_news_count(category):
    with db_lock:
        conn = sqlite3.connect('news.db')
        c = conn.cursor()
        if category == "전체":
            c.execute('SELECT COUNT(DISTINCT id) FROM news')
        else:
            c.execute('SELECT COUNT(DISTINCT id) FROM news WHERE category = ?', (category,))
        count = c.fetchone()[0]
        category_news_counts[category] = count
        conn.close()
    return count

def fetch_and_store_news(keyword, category):
    try:
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
        }
        params = {
            "query": keyword,
            "display": 100,
            "sort": "date"
        }
        
        response = requests.get(url, headers=headers, params=params)
        news_items = []
        
        if response.status_code == 200:
            items = response.json().get('items', [])
            with db_lock:
                conn = sqlite3.connect('news.db')
                c = conn.cursor()
                
                for news in items:
                    try:
                        # Clean HTML tags from title and description
                        title = news['title'].replace('<b>', '').replace('</b>', '')
                        description = news['description'].replace('<b>', '').replace('</b>', '')
                        
                        # Create a unique hash based on title and link
                        news_hash = hashlib.md5(f"{title}{news['link']}".encode()).hexdigest()
                        
                        # Check if news already exists
                        c.execute('SELECT id FROM news WHERE id = ?', (news_hash,))
                        if not c.fetchone():
                            try:
                                pub_date = datetime.strptime(news['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                                formatted_date = pub_date.isoformat()
                            except:
                                formatted_date = datetime.now().isoformat()
                            
                            c.execute('''INSERT INTO news 
                                        (id, keyword, title, description, link, pub_date, category, created_at)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                    (news_hash, keyword, title, description,
                                     news['link'], formatted_date, category,
                                     datetime.now().isoformat()))
                            
                            news_item = {
                                'id': news_hash,
                                'keyword': keyword,
                                'title': title,
                                'description': description,
                                'link': news['link'],
                                'pubDate': formatted_date,
                                'category': category,
                                'isNew': True
                            }
                            
                            news_items.append(news_item)
                            update_queue.put(news_item)
                            logger.info(f"New news item found for {keyword}: {title[:30]}...")
                    except Exception as e:
                        logger.error(f"Error processing news item: {str(e)}")
                        continue
                
                conn.commit()
                conn.close()
            
            # Update news count for the category
            update_news_count(category)
            if category != "전체":
                update_news_count("전체")
            
        return news_items
            
    except Exception as e:
        logger.error(f"Error fetching news for {keyword}: {str(e)}")
        return []

def background_news_fetcher():
    global collector_thread
    
    while not collector_thread.stopped():
        try:
            collector_thread.is_running = True
            collector_thread.status = "running"
            collector_thread.last_run = datetime.now()
            
            logger.info("Starting background news fetch cycle...")
            
            for category, keywords in list(SEARCH_CATEGORIES.items())[1:]:  # Skip "전체" category
                if collector_thread.stopped():
                    break
                    
                if keywords:  # Only process categories with keywords
                    collector_thread.current_category = category
                    for keyword in keywords:
                        if collector_thread.stopped():
                            break
                            
                        collector_thread.current_keyword = keyword
                        collector_thread.status = f"fetching news for {keyword}"
                        
                        try:
                            news_items = fetch_and_store_news(keyword, category)
                            logger.info(f"Found {len(news_items)} new items for {keyword}")
                            time.sleep(1)  # Delay between API calls
                        except Exception as e:
                            logger.error(f"Error in fetch cycle for {keyword}: {str(e)}")
                            time.sleep(5)  # Longer delay on error
                            continue
            
            collector_thread.current_category = None
            collector_thread.current_keyword = None
            collector_thread.status = "waiting"
            logger.info("Completed background news fetch cycle.")
            
            # Wait for 1 minute before next cycle
            for _ in range(60):  # 1 minute in 1-second increments
                if collector_thread.stopped():
                    break
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in background fetcher: {str(e)}")
            collector_thread.status = "error"
            time.sleep(60)
        finally:
            collector_thread.is_running = False

@app.route('/')
def index():
    # Update all category counts before rendering
    for category in SEARCH_CATEGORIES.keys():
        update_news_count(category)
    return render_template('news.html', categories=SEARCH_CATEGORIES, news_counts=category_news_counts)

@app.route('/get_news_counts')
def get_news_counts():
    return jsonify(category_news_counts)

@app.route('/search_news', methods=['POST'])
def search_news():
    try:
        data = request.get_json()
        keyword = data.get('keyword', '')
        category = data.get('category', '')
        
        conn = sqlite3.connect('news.db')
        c = conn.cursor()
        
        if category == "전체":
            c.execute('''SELECT * FROM news ORDER BY pub_date DESC''')
        elif keyword:  # If keyword is provided, search by keyword
            c.execute('''SELECT * FROM news WHERE keyword = ? ORDER BY pub_date DESC''', (keyword,))
        else:  # If only category is provided
            c.execute('''SELECT * FROM news WHERE category = ? ORDER BY pub_date DESC''', (category,))
            
        news_items = c.fetchall()
        conn.close()
        
        # Convert to list of dictionaries
        news = []
        seen = set()
        for item in news_items:
            if item[0] not in seen:  # Avoid duplicates using news_hash
                seen.add(item[0])
                news.append({
                    'id': item[0],
                    'keyword': item[1],
                    'title': item[2],
                    'description': item[3],
                    'link': item[4],
                    'pubDate': item[5],
                    'category': item[6]
                })
        
        return jsonify({"news": news})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stream')
def stream():
    def generate():
        while True:
            try:
                news = update_queue.get()
                yield f"data: {json.dumps(news)}\n\n"
            except Exception as e:
                print(f"Streaming error: {str(e)}")
                continue
    
    return app.response_class(generate(), mimetype='text/event-stream')

@app.route('/get_categories', methods=['GET'])
def get_categories():
    return jsonify(SEARCH_CATEGORIES)

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/get_database_stats')
def get_database_stats():
    try:
        conn = sqlite3.connect('news.db')
        c = conn.cursor()
        
        # Get total number of news
        c.execute('SELECT COUNT(DISTINCT id) FROM news')
        total_news = c.fetchone()[0]
        
        # Get news count per category
        c.execute('''
            SELECT category, COUNT(DISTINCT id) as count 
            FROM news 
            GROUP BY category
        ''')
        category_counts = dict(c.fetchall())
        
        # Get news count per keyword
        c.execute('''
            SELECT keyword, COUNT(DISTINCT id) as count 
            FROM news 
            GROUP BY keyword
        ''')
        keyword_counts = dict(c.fetchall())
        
        conn.close()
        
        return jsonify({
            'total_news': total_news,
            'category_counts': category_counts,
            'keyword_counts': keyword_counts,
            'total_categories': len(SEARCH_CATEGORIES),
            'categories': SEARCH_CATEGORIES
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reset_database', methods=['POST'])
def reset_database():
    try:
        # Stop the background fetcher temporarily
        time.sleep(2)  # Wait for any ongoing operations to complete
        
        with db_lock:  # Acquire the lock before accessing the database
            conn = sqlite3.connect('news.db')
            c = conn.cursor()
            
            # Delete all records from the news table
            c.execute('DELETE FROM news')
            
            # Check if sqlite_sequence exists before trying to delete from it
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            if c.fetchone():
                c.execute('DELETE FROM sqlite_sequence WHERE name="news"')
            
            conn.commit()
            conn.close()
            
            # Reset all category news counts
            for category in SEARCH_CATEGORIES.keys():
                category_news_counts[category] = 0
        
        return jsonify({'success': True, 'message': '데이터베이스가 초기화되었습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/collector/status')
def get_collector_status():
    """Get the current status of the news collector thread"""
    if collector_thread:
        return jsonify(collector_thread.get_status())
    return jsonify({"status": "not running"})

@app.route('/collector/restart', methods=['POST'])
def restart_collector():
    """Restart the news collector thread"""
    global collector_thread
    
    try:
        if collector_thread:
            collector_thread.stop()
            time.sleep(2)  # Wait for thread to stop
        
        collector_thread = NewsCollectorThread(target=background_news_fetcher, daemon=True)
        collector_thread.start()
        
        return jsonify({
            "success": True,
            "message": "News collector thread restarted successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logger.error("Naver API credentials not set. Please set NAVER_CLIENT_ID and NAVER_CLIENT_SECRET in .env file")
    
    # Initialize database
    init_db()
    
    # Start background news fetcher thread
    collector_thread = NewsCollectorThread(target=background_news_fetcher, daemon=True)
    collector_thread.start()
    logger.info("News collector thread started")
    
    app.run(debug=True, threaded=True) 