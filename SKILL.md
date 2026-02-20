# Skill: RSS Heartbeat (Universal Installer)

## 📖 Description
A **self-installing, configurable RSS aggregation heartbeat** for Nanobot. 
Automatically fetches articles from your OPML feeds, converts them to Markdown/JSON (Schema v0.2), and syncs to GitHub daily.

**Key Features:**
- **Zero-Config Install**: Run one command to set up everything (cloning, config, scheduling).
- **Config-Driven**: Customize feeds, schedule, and output via `config.yaml`.
- **Schema v0.2**: Outputs structured JSON with SHA1 IDs, language detection, and reading time.
- **GitHub Sync**: Automatically commits and pushes digests to your repository.
- **Silent Operation**: Runs via macOS `launchd` in the background; logs errors only.

## 🚀 Installation (One-Command)

Any Nanobot user can install this heartbeat by running the following command in their terminal (or asking their AI agent to run it):

### Option A: Interactive Mode (Recommended)
```bash
cd ~/.nanobot/workspace
git clone https://github.com/jason-huanghao/daily-rss-digest.git skills/rss-heartbeat-instance
cd skills/rss-heartbeat-instance
python install_heartbeat.py
```
*The installer will ask for your OPML path, preferred time, and GitHub details.*

### Option B: Command Line Arguments
```bash
python install_heartbeat.py \
  --repo "jason-huanghao/daily-rss-digest" \
  --opml "~/my-feeds.opml" \
  --schedule "0 6 * * *"
```

### Option C: Via Nanobot Chat
Simply say to your Nanobot agent:
> "Install the RSS Heartbeat skill from `jason-huanghao/daily-rss-digest` using my `~/feeds.opml` file at 6 AM."

*(The agent will execute the installer script automatically.)*

## ⚙️ Configuration

After installation, edit `config.yaml` in the installation directory to customize behavior:

```yaml
# Schedule (Cron format)
schedule: "0 4 * * *"  # 4:00 AM Daily

# Inputs
opml_path: "~/feeds.opml"  # Absolute path recommended

# GitHub Sync (Optional)
github_user: "your-username"
github_repo: "your-repo-name"
github_token_env: "GITHUB_TOKEN"  # Env var containing your PAT

# Processing
fetch_hours: 24          # Look back 24 hours for articles
content_limit: 15000     # Max chars per article
max_workers_percent: 0.8 # CPU usage (80%)
```

## 📂 Output Structure

The heartbeat generates two files daily in the `output_dir`:

1. **`json/YYYY-MM-DD.json`**: Raw data in **Knowledge Item Schema v0.2**.
   - Keys: SHA1 hash of URL.
   - Fields: `source_type`, `info_layer`, `language`, `importance_score`, `metadata`.
2. **`digest/YYYY-MM-DD.md`**: Human-readable Markdown digest grouped by source.

## 🛠️ Manual Management

### Uninstall
To stop the heartbeat:
```bash
launchctl unload ~/Library/LaunchAgents/com.nanobot.rss-heartbeat-user.plist
rm ~/Library/LaunchAgents/com.nanobot.rss-heartbeat-user.plist
rm -rf ~/.nanobot/workspace/skills/rss-heartbeat-instance
```

### Run Manually
To test or run immediately:
```bash
cd ~/.nanobot/workspace/skills/rss-heartbeat-instance
uv run python rss_heartbeat.py
```

### View Logs
```bash
tail -f ~/.nanobot/workspace/skills/rss-heartbeat-instance/heartbeat.log
```

## 🤝 Contributing
This skill is maintained by **jason-huanghao**. 
Repo: [github.com/jason-huanghao/daily-rss-digest](https://github.com/jason-huanghao/daily-rss-digest)

## 📝 Changelog
- **v2.0**: Refactored to be config-driven and universally installable.
- **v1.5**: Added Schema v0.2 support (SHA1 IDs, language detection).
- **v1.0**: Initial monorepo heartbeat implementation.
