import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import praw, tweepy, and twikit safely
try:
    import praw
except ImportError:
    praw = None

try:
    import tweepy
except ImportError:
    tweepy = None

try:
    import twikit
except ImportError:
    twikit = None


def get_reddit_posts(ticker_symbol, limit=50):
    """
    Searches Reddit subreddits ('IndianStreetBets', 'DalalStreetTalks', 'IndiaInvestments')
    for recent posts mentioning the specific stock ticker.
    """
    clean_ticker = _normalize_ticker(ticker_symbol)
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "TradingBotRetailSentiment/1.0")

    if not client_id or not client_secret:
        logger.warning("[Reddit] Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET environment variables. Returning empty list.")
        return []

    if praw is None:
        logger.warning("[Reddit] praw package is not installed. Returning empty list.")
        return []

    subreddits = ['IndianStreetBets', 'DalalStreetTalks', 'IndiaInvestments']
    posts_text = []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        
        cutoff = datetime.now(timezone.utc).timestamp() - timedelta(hours=24).total_seconds()
        for sub_name in subreddits:
            try:
                subreddit = reddit.subreddit(sub_name)
                for post in subreddit.search(clean_ticker, limit=limit, time_filter="day"):
                    created_utc = getattr(post, "created_utc", None)
                    if created_utc is not None and created_utc < cutoff:
                        continue
                    combined = f"{post.title} {post.selftext}".strip()
                    if combined:
                        posts_text.append(combined)
            except Exception as e:
                logger.error(f"[Reddit] Error searching subreddit {sub_name}: {e}")

    except Exception as e:
        logger.error(f"[Reddit] Error initializing PRAW Reddit client: {e}")

    logger.info(f"[Reddit] Fetched {len(posts_text)} posts for {clean_ticker}")
    return posts_text


async def _fetch_tweets_twikit(clean_ticker, max_results=50):
    """Asynchronous tweet fetching using twikit web client (free, no paid API needed)."""
    username = os.getenv("TWITTER_USERNAME")
    email = os.getenv("TWITTER_EMAIL")
    password = os.getenv("TWITTER_PASSWORD")

    if not username or not password:
        logger.warning("[Twitter/twikit] Missing TWITTER_USERNAME or TWITTER_PASSWORD in environment.")
        return []

    cookies_path = Path(__file__).resolve().parent / "data" / "twitter_cookies.json"
    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    client = twikit.Client("en-US")

    # Load session cookies if available to avoid aggressive logins
    logged_in = False
    if cookies_path.exists():
        try:
            client.load_cookies(str(cookies_path))
            logged_in = True
        except Exception as e:
            logger.debug(f"[Twitter/twikit] Could not load cookies: {e}")

    if not logged_in:
        try:
            await client.login(
                auth_info_1=username,
                auth_info_2=email,
                password=password,
                cookies_file=str(cookies_path)
            )
        except Exception as e:
            logger.error(f"[Twitter/twikit] Login failed: {e}")
            return []

    tweets_text = []
    try:
        query = f"${clean_ticker} OR #{clean_ticker}"
        results = await client.search_tweet(query, "Latest", count=max_results)
        if results:
            for tweet in results:
                t_text = getattr(tweet, "text", "") or ""
                t_text = t_text.strip()
                if t_text:
                    tweets_text.append(t_text)
    except Exception as e:
        logger.error(f"[Twitter/twikit] Search error for {clean_ticker}: {e}")

    return tweets_text


def get_tweets(ticker_symbol, max_results=50):
    """
    Searches Twitter (X) for recent tweets mentioning the ticker cash-tag/hashtag.
    Checks Tweepy first if TWITTER_BEARER_TOKEN is provided, otherwise falls back to twikit.
    """
    clean_ticker = _normalize_ticker(ticker_symbol)

    # 1. Check Tweepy Bearer Token first if present
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    if bearer_token and tweepy is not None:
        adjusted_max = max(10, min(100, max_results))
        tweets_text = []
        try:
            client = tweepy.Client(bearer_token=bearer_token)
            query = f"(${clean_ticker} OR #{clean_ticker}) -is:retweet"
            start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            response = client.search_recent_tweets(
                query=query,
                max_results=adjusted_max,
                start_time=start_time,
            )
            if response and response.data:
                for tweet in response.data:
                    text = tweet.text.strip()
                    if text:
                        tweets_text.append(text)
            logger.info(f"[Twitter/tweepy] Fetched {len(tweets_text)} tweets for {clean_ticker}")
            return tweets_text
        except Exception as e:
            logger.error(f"[Twitter/tweepy] Error fetching tweets for {clean_ticker}: {e}")

    # 2. Free twikit web scraper
    if twikit is not None and os.getenv("TWITTER_USERNAME") and os.getenv("TWITTER_PASSWORD"):
        try:
            tweets = asyncio.run(_fetch_tweets_twikit(clean_ticker, max_results=max_results))
            logger.info(f"[Twitter/twikit] Fetched {len(tweets)} tweets for {clean_ticker}")
            return tweets
        except Exception as e:
            logger.error(f"[Twitter/twikit] Exception during search: {e}")

    logger.warning("[Twitter] No active Twitter credentials found. Returning empty list.")
    return []


def clean_social_text(text):
    """Removes URLs, special characters, and normalizes whitespace in text."""
    if not text:
        return ""
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'[^a-zA-Z0-9\s.,!?\'"-]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _normalize_ticker(ticker_symbol):
    """Normalize symbols such as CIPLA.NS for social search queries."""
    if not isinstance(ticker_symbol, str) or not ticker_symbol.strip():
        raise ValueError("ticker_symbol must be a non-empty string")
    return ticker_symbol.strip().split(".", 1)[0].upper()


def get_social_text(ticker_symbol):
    """
    Aggregates Reddit posts and Twitter tweets for a given stock ticker,
    removes URLs and special characters, and returns a single clean list of strings.
    """
    _normalize_ticker(ticker_symbol)
    logger.info(f"[SocialScraper] Starting social sentiment ingestion for ticker: {ticker_symbol}")
    
    reddit_posts = get_reddit_posts(ticker_symbol)
    tweets = get_tweets(ticker_symbol)

    raw_combined = reddit_posts + tweets
    clean_list = []

    for raw in raw_combined:
        cleaned = clean_social_text(raw)
        if len(cleaned) > 10:
            clean_list.append(cleaned)

    logger.info(f"[SocialScraper] Completed social text ingestion. Total clean items: {len(clean_list)}")
    return clean_list


if __name__ == "__main__":
    import sys
    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "CIPLA"
    print(f"=== Running Social Scraper for {test_ticker} ===")
    results = get_social_text(test_ticker)
    print(f"Retrieved {len(results)} cleaned retail chatter items:")
    for i, item in enumerate(results[:5], 1):
        print(f"  [{i}] {item}")
