#!/usr/bin/env python3
"""
RSS Heartbeat: Daily Fetch, Summarize, and Git Commit
Config-Driven Version (Universal Installer Ready)

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
import yaml  # New dependency for config

# Attempt to import langdetect, fallback to 'en' if missing
try:
    from langdetect import detect
    LANG_DETECT_AVAILABLE = True
except ImportError:
    LANG_DETECT_AVAILABLE = False

# --- Configuration Loading ---
def load_config():
    """Loads config from config.yaml, then env vars, then defaults."""
    script_dir = Path(__file__).parent
    config_file = script_dir / "config.yaml"
    
    # Defaults
    config = {
        "schedule": "0 4 * * *",
        "opml_path": str(script_dir / "feeds.opml"),
        "github_user": None,
        "github_repo": None,
        "github_token_env": "GITHUB_TOKEN",
        "output_dir": str(script_dir),
        "fetch_hours": 24,
        "content_limit": 15000,
        "max_workers_percent": 0.8
    }

    # Load from YAML if exists
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config.update(yaml_config)
            print(f"✅ Loaded config from {config_file}")
        except Exception as e:
            print(f"⚠️ Error reading config.yaml: {e}. Using defaults.")
    
    # Resolve paths relative to script dir if not absolute
    if not os.path.isabs(config['opml_path']):
        config['opml_path'] = str(script_dir / config['opml_path'])
    
    if not os.path.isabs(config['output_dir']):
        config['output_dir'] = str(script_dir / config['output_dir'])

    # Load Token from Env
    token_env = config.get('github_token_env', 'GITHUB_TOKEN')
    config['github_token'] = os.getenv(token_env)

    return config

CONFIG = load_config()

# --- Helper Functions ---
def parse_opml(opml_path):
    if not os.path.exists(opml_path):
        raise FileNotFoundError(f"OPML file not found: {opml_path}")
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
            limit = CONFIG.get('content_limit', 15000)
            return md_content[:limit] + ("..." if len(md_content) > limit else "")
    except:
        pass
    return None

def detect_language(text):
    if not LANG_DETECT_AVAILABLE or not text:
        return "en"
    try:
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
            
            item_id = hashlib.sha1(url.encode('utf-8')).hexdigest()
            summary_raw = entry.get('summary', '') or entry.get('description', '')
            summary_text = ""
            if summary_raw:
                summary_text = BeautifulSoup(summary_raw, 'html.parser').get_text(separator=' ', strip=True)[:500]
            
            full_content = fetch_full_content(url)
            if not full_content:
                full_content = summary_text
            
            lang = detect_language(full_content or summary_text)
            reading_time = calculate_reading_time(full_content or summary_text)

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
    
    articles = list(items_dict.values())
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
                safe_summary = item['summary'].replace('>', r'\>')
                lines.append(f" > {safe_summary}")
        lines.append("")
    
    return "\n".join(lines)

def git_sync_and_commit(base_dir, today, json_filename, md_filename):
    user = CONFIG.get('github_user')
    repo = CONFIG.get('github_repo')
    token = CONFIG.get('github_token')
    
    if not user or not repo or not token:
        print("⚠️ GitHub sync disabled (missing config). Local files saved only.")
        github_url = f"file://{base_dir}/{md_filename}"
        return github_url

    print("🔄 Syncing with GitHub...")
    # Safe pull
    os.system(f"cd '{base_dir}' && git pull --rebase origin main >/dev/null 2>&1 || (git rebase --abort >/dev/null 2>&1 && git pull origin main >/dev/null 2>&1)")
    
    status = os.popen(f"cd '{base_dir}' && git status --porcelain").read()
    if status:
        print("📝 Changes detected. Committing...")
        os.system(f"cd '{base_dir}' && git add {json_filename} {md_filename}")
        # Temporarily set user info if not set
        os.system(f"cd '{base_dir}' && git config user.name 'Nanobot Heartbeat' >/dev/null 2>&1")
        os.system(f"cd '{base_dir}' && git config user.email 'heartbeat@nanobot.local' >/dev/null 2>&1")
        os.system(f"cd '{base_dir}' && git commit -m 'Daily RSS digest: {today}'")
        
        print("⬆️ Pushing to GitHub...")
        # Use token for auth
        push_result = os.system(f"cd '{base_dir}' && git push https://{user}:{token}@github.com/{user}/{repo}.git main")
        
        if push_result == 0:
            github_url = f"https://github.com/{user}/{repo}/blob/main/{md_filename}"
        else:
            print("❌ Git push failed.", file=sys.stderr)
            github_url = f"file://{base_dir}/{md_filename}"
    else:
        print("✨ No new changes. Skipping commit.")
        github_url = f"https://github.com/{user}/{repo}/blob/main/{md_filename}"
    
    return github_url

def main():
    fetched_at = datetime.now(timezone.utc).isoformat()
    print(f"🚀 RSS Heartbeat started at {fetched_at}")
    
    base_dir = Path(CONFIG['output_dir'])
    opml_path = Path(CONFIG['opml_path'])
    
    if not opml_path.exists():
        print(f"❌ Error: OPML file not found at {opml_path}", file=sys.stderr)
        sys.exit(1)
    
    # Ensure output folders exist
    json_dir = base_dir / "json"
    digest_dir = base_dir / "digest"
    json_dir.mkdir(exist_ok=True)
    digest_dir.mkdir(exist_ok=True)
    
    feeds = parse_opml(opml_path)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CONFIG.get('fetch_hours', 24))
    max_workers = max(1, int((os.cpu_count() or 4) * CONFIG.get('max_workers_percent', 0.8)))
    
    print(f"Fetching {len(feeds)} feeds (last {CONFIG.get('fetch_hours', 24)}h) with {max_workers} workers...")
    
    all_items = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
    
    # Write JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved: {json_path}")
    
    # Write Markdown
    summary_md = generate_summary(all_items)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(summary_md)
    print(f"💾 Saved: {md_path}")
    
    # Git Sync
    github_url = git_sync_and_commit(base_dir, today, str(json_path.relative_to(base_dir)), str(md_path.relative_to(base_dir)))
    
    print("\n" + "="*50)
    print(f"✅ DAILY DIGEST READY: {github_url}")
    print("="*50)

if __name__ == "__main__":
    main()
