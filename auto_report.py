import os
import sys
import json
import subprocess
import datetime
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AutoReporter] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env_file():
    """Load key-value pairs from .env if present without external dependencies."""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'").strip()
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception as e:
        logger.warning(f"Could not load .env file: {e}")


def get_report_date():
    """Determines the correct report date (skips weekends)."""
    today = datetime.datetime.now()
    if today.weekday() == 5:  # Saturday
        target = today - datetime.timedelta(days=1)
        logger.info(f"Weekend (Saturday). Using Friday: {target.strftime('%Y-%m-%d')}")
    elif today.weekday() == 6:  # Sunday
        target = today - datetime.timedelta(days=2)
        logger.info(f"Weekend (Sunday). Using Friday: {target.strftime('%Y-%m-%d')}")
    else:
        target = today
    return target.strftime("%Y-%m-%d")


def generate_report(date_str):
    """Runs daily_reporter.py to generate the report for the given date."""
    logger.info(f"Generating daily report for {date_str}...")
    result = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "daily_reporter.py"), date_str],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        logger.error(f"daily_reporter.py failed:\n{result.stderr}")
        return False
    logger.info(result.stdout.strip())
    return True


def git_commit_file(filepath, message):
    """Stages and commits a single file with the given message."""
    rel_path = os.path.relpath(filepath, BASE_DIR)
    subprocess.run(["git", "add", rel_path], cwd=BASE_DIR, check=True,
                    capture_output=True, text=True)
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=BASE_DIR, capture_output=True, text=True
    )
    if result.returncode == 0:
        logger.info(f"Committed: {rel_path}")
        return True
    elif "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
        logger.info(f"No changes to commit for {rel_path}")
        return False
    else:
        logger.warning(f"Commit issue for {rel_path}: {result.stderr.strip()}")
        return False


def git_push(pat=None):
    """
    Pushes committed changes to origin/main.
    Uses PAT if provided to avoid GUI credential manager popups that hang background processes.
    """
    remote_proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=BASE_DIR, capture_output=True, text=True
    )
    remote_url = remote_proc.stdout.strip()
    if not remote_url:
        logger.error("No origin remote found.")
        return False

    push_url = remote_url
    if pat:
        if remote_url.startswith("https://"):
            # Format: https://<PAT>@github.com/owner/repo.git
            clean_url = remote_url.replace("https://", "")
            if "@" in clean_url:
                clean_url = clean_url.split("@", 1)[1]
            push_url = f"https://{pat}@{clean_url}"
            logger.info("Using PAT authentication for push.")

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    logger.info("Pushing to origin/main...")
    result = subprocess.run(
        ["git", "push", push_url, "main"],
        cwd=BASE_DIR, capture_output=True, text=True,
        env=env, timeout=60
    )
    if result.returncode == 0:
        logger.info(f"Push successful!\n{result.stderr.strip()}")
        return True
    else:
        logger.error(f"Push failed:\n{result.stderr.strip()}")
        return False


def run_auto_report(date_str=None, push=True, pat=None):
    """Main entry point: generate report, commit each file, push to GitHub."""
    load_env_file()
    target_date = date_str or get_report_date()
    logger.info(f"=== Auto Report & Push for {target_date} ===")

    # 1. Generate the report
    report_file = os.path.join(BASE_DIR, "reports", f"daily_report_{target_date}.md")
    if os.path.exists(report_file):
        logger.info(f"Report already exists: {report_file}. Skipping generation.")
    else:
        if not generate_report(target_date):
            logger.error("Report generation failed. Aborting.")
            return False

    # 2. Commit each modified/new file separately
    commits_made = 0

    # Report file
    if os.path.exists(report_file):
        if git_commit_file(report_file, f"report({target_date}): Add daily performance report"):
            commits_made += 1

    # Performance journal
    journal_file = os.path.join(BASE_DIR, "reports", "performance_journal.md")
    if os.path.exists(journal_file):
        if git_commit_file(journal_file, f"chore(journal): Append {target_date} entry to performance journal"):
            commits_made += 1

    # README metrics
    readme_file = os.path.join(BASE_DIR, "README.md")
    if os.path.exists(readme_file):
        if git_commit_file(readme_file, f"docs(README): Update live performance metrics for {target_date}"):
            commits_made += 1

    logger.info(f"Total report commits made: {commits_made}")

    # 3. Push to GitHub
    if push:
        token = pat or os.environ.get("GITHUB_PAT") or os.environ.get("GITHUB_TOKEN")
        if not token:
            logger.warning("GITHUB_PAT / GITHUB_TOKEN not detected in environment or .env.")
            logger.warning("Please supply via --pat <token> or add GITHUB_PAT=your_token to .env to push automatically.")
        return git_push(token)
    else:
        logger.info("Push skipped (push=False).")
        return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Auto-generate daily report, commit, and push to GitHub.")
    parser.add_argument("--date", type=str, default=None, help="Report date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--no-push", action="store_true", help="Skip git push (commit only).")
    parser.add_argument("--pat", type=str, default=None, help="GitHub Personal Access Token for headless pushing.")
    args = parser.parse_args()

    success = run_auto_report(date_str=args.date, push=not args.no_push, pat=args.pat)
    sys.exit(0 if success else 1)
