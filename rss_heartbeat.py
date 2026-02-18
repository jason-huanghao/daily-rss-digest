#!/usr/bin/env python3
"""
RSS Heartbeat: Daily Fetch, Summarize, and GitHub Upload
Runs at 4:00 AM daily.
"""

import os
import sys
import json
import time
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Third-party imports
import feedparser
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import re

# Load environment variables
load_dotenv()

# --- Configuration ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = "jason-huanghao"
REPO_NAME = "daily-rss-digest"
OPML_FILE = "feeds.opml"
LOG_DIR = "log"
JSON_FOLDER = "json"
DIGEST_FOLDER = "digest"
MAX_WORKERS = max(1, int((os.cpu_count() or 4) * 0.8))
FETCH_HOURS = 24
CONTENT_LIMIT = 15000

# --- Helper Functions ---

def parse_opml(opml_path):
    tree = ET.parse(opml_path)
    root = tree.getroot()
    feeds = []
    for outline in root.iter('outline'):
        xml_url = outline.get('xmlUrl')
        if xml_url:
            feeds.append({
                'title': outline.get('title') or outline.get('text', 'Unknown'),
                'xml_url': xml_url
            })
    return feeds

def parse_date(entry):
    for field in ['published_parsed', 'updated_parsed']:
        t = getattr(entry, field, None)
        if t:
            try:
                return datetime(*t[:6]).replace(tzinfo=timezone.utc)
            except:
                continue
    return None

def fetch_full_content(url, timeout=8):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        content = soup.select_one('article') or soup.select_one('main') or soup.body
        if content:
            md_content = md(str(content), heading_style='ATX', strip=['a'])
            md_content = re.sub(r'\n{3,}', '\n\n', md_content).strip()
            return md_content[:CONTENT_LIMIT] + ("..." if len(md_content) > CONTENT_LIMIT else "")
    except:
        pass
    return None

def fetch_feed(feed, cutoff):
    articles = []
    try:
        data = feedparser.parse(feed['xml_url'])
        for entry in data.entries:
            pub = parse_date(entry)
            if not pub or pub < cutoff:
                continue
            url = entry.get('link')
            if not url:
                continue
            summary = entry.get('summary', '') or entry.get('description', '')
            if summary:
                summary = BeautifulSoup(summary, 'html.parser').get_text(separator=' ', strip=True)[:500]
            
            full = fetch_full_content(url)
            articles.append({
                'title': entry.get('title', 'No Title'),
                'url': url,
                'source': feed['title'],
                'published': pub.isoformat(),
                'summary': summary,
                'content': full
            })
    except Exception as e:
        print(f"Error fetching {feed['title']}: {e}")
    return articles

def generate_summary(articles):
    if not articles:
        return "# Daily Digest\n\nNo new articles found today."
    
    # Group by source
    by_source = {}
    for a in articles:
        by_source.setdefault(a['source'], []).append(a)
    
    lines = [f"# Daily Tech Digest ({datetime.now().strftime('%Y-%m-%d')})", "", f"**{len(articles)} articles from {len(by_source)} sources**", ""]
    
    for source, items in sorted(by_source.items()):
        lines.append(f"## {source}")
        for item in items:
            lines.append(f"- [{item['title']}]({item['url']})")
            if item['summary']:
                lines.append(f"  > {item['summary']}")
        lines.append("")
    
    return "\n".join(lines)

def upload_to_github(filename, content, folder):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{folder}/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    # Check if file exists to get SHA
    sha = None
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json().get('sha')
    
    data = {
        "message": f"Daily digest: {filename}",
        "content": requests.utils.b64encode(content.encode('utf-8')).decode('utf-8'),
        "branch": "main"
    }
    if sha:
        data["sha"] = sha
    
    r = requests.put(url, json=data, headers=headers)
    r.raise_for_status()
    return f"https://github.com/{GITHUB_USER}/{REPO_NAME}/blob/main/{folder}/{filename}"

def main():
    print(f"🚀 RSS Heartbeat started at {datetime.now().isoformat()}")
    
    # Paths
    base_dir = Path(__file__).parent
    opml_path = base_dir / OPML_FILE
    if not opml_path.exists():
        print(f"Error: {opml_path} not found")
        sys.exit(1)
    
    os.makedirs(base_dir / LOG_DIR, exist_ok=True)
    
    feeds = parse_opml(opml_path)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FETCH_HOURS)
    
    print(f"Fetching {len(feeds)} feeds (last {FETCH_HOURS}h) with {MAX_WORKERS} workers...")
    
    all_articles = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_feed, f, cutoff): f for f in feeds}
        for i, future in enumerate(as_completed(futures)):
            try:
                items = future.result()
                all_articles.extend(items)
                print(f"[{i+1}/{len(feeds)}] {futures[future]['title']}: {len(items)} articles")
            except Exception as e:
                print(f"Task failed: {e}")
    
    print(f"\nTotal articles: {len(all_articles)}")
    
    today = datetime.now().strftime("%Y-%m-%d")
    json_name = f"{today}.json"
    md_name = f"{today}.md"
    
    # Save JSON locally
    json_path = base_dir / LOG_DIR / JSON_FOLDER
    json_path.mkdir(parents=True, exist_ok=True)
    with open(json_path / json_name, 'w') as f:
        json.dump(all_articles, f, indent=2)
    
    # Generate Summary
    summary_md = generate_summary(all_articles)
    
    # Upload to GitHub
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN not found in .env")
        sys.exit(1)
    
    try:
        # Upload JSON
        with open(json_path / json_name, 'r') as f:
            json_content = f.read()
        json_url = upload_to_github(json_name, json_content, JSON_FOLDER)
        print(f"JSON uploaded: {json_url}")
        
        # Upload MD
        md_url = upload_to_github(md_name, summary_md, DIGEST_FOLDER)
        print(f"Digest uploaded: {md_url}")
        
        # FINAL OUTPUT FOR HEARTBEAT
        print("\n" + "="*50)
        print(f"✅ DAILY DIGEST READY: {md_url}")
        print("="*50)
        
    except Exception as e:
        print(f"GitHub upload failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()