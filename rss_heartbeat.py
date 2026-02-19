#!/usr/bin/env python3
"""
RSS Heartbeat: Daily Fetch, Summarize, and Git Commit
Runs at 4:00 AM daily.
Architecture: Permanent Local Mirror (Monorepo)
Schema: Knowledge Item v0.2
"""
import os
import sys
import json
import time
import hashlib
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import feedparser
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import re

# Attempt to import langdetect, fallback to 'en' if missing
try:
    from langdetect import detect
    LANG_DETECT_AVAILABLE = True
except ImportError:
    LANG_DETECT_AVAILABLE = False

# Load environment variables (from parent dir via shell wrapper)
load_dotenv()

# --- Configuration ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = "jason-huanghao"
REPO_NAME = "daily-rss-digest"
OPML_FILE = "feeds.opml"
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

def detect_language(text):
    if not LANG_DETECT_AVAILABLE or not text:
        return "en"
    try:
        # Use first 1000 chars for speed
        return detect(text[:1000])
    except:
        return "en"

def calculate_reading_time(content):
    words = len(content.split())
    return max(1, round(words / 200))

def fetch_feed(feed, cutoff, fetched_at):
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
            
            # Generate Global ID
            item_id = hashlib.sha1(url.encode('utf-8')).hexdigest()
            
            summary_raw = entry.get('summary', '') or entry.get('description', '')
            summary_text = ""
            if summary_raw:
                summary_text = BeautifulSoup(summary_raw, 'html.parser').get_text(separator=' ', strip=True)[:500]
            
            full_content = fetch_full_content(url)
            if not full_content:
                full_content = summary_text # Fallback if scrape fails
            
            lang = detect_language(full_content or summary_text)
            reading_time = calculate_reading_time(full_content or summary_text)

            # Knowledge Item Schema v0.2
            item = {
                "id": item_id,
                "source_type": "rss",
                "info_layer": "content",
                "source_name": feed['title'],
                "title": entry.get('title', 'No Title'),
                "url": url,
                "published_at": pub.isoformat() if pub else None,
                "fetched_at": fetched_at,
                "language": lang,
                "content": full_content,
                "summary": summary_text,
                "tags": [],
                "importance_score": 0.4,
                "metadata": {
                    "reading_time_minutes": reading_time
                }
            }
            articles.append((item_id, item))
    except Exception as e:
        print(f"Error fetching {feed['title']}: {e}", file=sys.stderr)
    return articles

def generate_summary(items_dict):
    if not items_dict:
        return "# Daily Digest\n\nNo new articles found today."
    
    # Convert dict values to list for processing
    articles = list(items_dict.values())
    
    # Group by source
    by_source = {}
    for a in articles:
        by_source.setdefault(a['source_name'], []).append(a)
    
    lines = [
        f"# Daily Tech Digest ({datetime.now().strftime('%Y-%m-%d')})",
        "",
        f"**{len(articles)} articles from {len(by_source)} sources**",
        ""
    ]
    
    for source, items in sorted(by_source.items()):
        lines.append(f"## {source}")
        for item in items:
            lines.append(f"- [{item['title']}]({item['url']})")
            if item['summary']:
                # Escape > in summary to avoid breaking markdown blockquote
                safe_summary = item['summary'].replace('>', '\>')
                lines.append(f"  > {safe_summary}")
        lines.append("")
    
    return "\n".join(lines)

def main():
    fetched_at = datetime.now(timezone.utc).isoformat()
    print(f"🚀 RSS Heartbeat started at {fetched_at}")
    
    # Paths (Relative to script location)
    base_dir = Path(__file__).parent
    opml_path = base_dir / OPML_FILE
    
    if not opml_path.exists():
        print(f"Error: {opml_path} not found", file=sys.stderr)
        sys.exit(1)
    
    # Ensure output folders exist
    json_dir = base_dir / JSON_FOLDER
    digest_dir = base_dir / DIGEST_FOLDER
    json_dir.mkdir(exist_ok=True)
    digest_dir.mkdir(exist_ok=True)
    
    feeds = parse_opml(opml_path)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FETCH_HOURS)
    
    print(f"Fetching {len(feeds)} feeds (last {FETCH_HOURS}h) with {MAX_WORKERS} workers...")
    
    all_items = {} # Dict keyed by SHA1 ID
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_feed, f, cutoff, fetched_at): f for f in feeds}
        for i, future in enumerate(as_completed(futures)):
            try:
                items = future.result()
                for item_id, item in items:
                    all_items[item_id] = item
                print(f"[{i+1}/{len(feeds)}] {futures[future]['title']}: {len(items)} articles")
            except Exception as e:
                print(f"Task failed: {e}", file=sys.stderr)
    
    print(f"\nTotal unique articles: {len(all_items)}")
    
    today = datetime.now().strftime("%Y-%m-%d")
    json_filename = f"{today}.json"
    md_filename = f"{today}.md"
    
    json_path = json_dir / json_filename
    md_path = digest_dir / md_filename
    
    # Write JSON (Schema v0.2)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved: {json_path}")
    
    # Generate & Write Markdown
    summary_md = generate_summary(all_items)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(summary_md)
    print(f"💾 Saved: {md_path}")
    
    # Git Workflow (Sync, Commit, Push)
    print("🔄 Syncing with GitHub...")
    os.system(f"cd '{base_dir}' && git pull --rebase origin main || (git rebase --abort && git pull origin main)")
    
    # Check for changes
    status = os.popen(f"cd '{base_dir}' && git status --porcelain").read()
    if status:
        print("📝 Changes detected. Committing...")
        os.system(f"cd '{base_dir}' && git add {JSON_FOLDER} {DIGEST_FOLDER}")
        os.system(f"cd '{base_dir}' && git commit -m 'Daily RSS digest: {today}'")
        print("⬆️ Pushing to GitHub...")
        push_result = os.system(f"cd '{base_dir}' && git push origin main")
        if push_result == 0:
            github_url = f"https://github.com/{GITHUB_USER}/{REPO_NAME}/blob/main/{DIGEST_FOLDER}/{md_filename}"
            print("\n" + "="*50)
            print(f"✅ DAILY DIGEST READY: {github_url}")
            print("="*50)
        else:
            print("❌ Git push failed.", file=sys.stderr)
            sys.exit(1)
    else:
        print("✨ No new changes. Skipping commit.")
        github_url = f"https://github.com/{GITHUB_USER}/{REPO_NAME}/blob/main/{DIGEST_FOLDER}/{md_filename}"
        print("\n" + "="*50)
        print(f"✅ DAILY DIGEST READY (No new content): {github_url}")
        print("="*50)

if __name__ == "__main__":
    main()
