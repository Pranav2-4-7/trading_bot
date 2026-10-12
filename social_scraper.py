import os
import re
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import praw and tweepy safely
try:
    import praw
except ImportError:
    praw = None

try:
    import tweepy
except ImportError:
    tweepy = None


def get_reddit_posts(ticker_symbol, limit=50):
    """
    Searches Reddit subreddits ('IndianStreetBets', 'DalalStreetTalks', 'IndiaInvestments')
    for recent posts mentioning the specific stock ticker.
    
    Args:
        ticker_symbol (str): Stock ticker (e.g., 'CIPLA' or 'CIPLA.NS').
        limit (int): Maximum number of posts to fetch per subreddit.
        
    Returns:
        list: List of strings containing post titles and body text (selftext).
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
                # Reddit's day filter is coarse; enforce a rolling 24-hour window.
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


def get_tweets(ticker_symbol, max_results=50):
    """
    Searches Twitter (X) for recent tweets mentioning the ticker cash-tag/hashtag filtering out retweets.
    
    Args:
        ticker_symbol (str): Stock ticker (e.g., 'CIPLA' or 'CIPLA.NS').
        max_results (int): Maximum number of tweets to fetch (10 to 100 for API v2).
        
    Returns:
        list: List of strings containing tweet text.
    """
    clean_ticker = _normalize_ticker(ticker_symbol)
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

    if not bearer_token:
        logger.warning("[Twitter] Missing TWITTER_BEARER_TOKEN environment variable. Returning empty list.")
        return []

    if tweepy is None:
        logger.warning("[Twitter] tweepy package is not installed. Returning empty list.")
        return []

    # API v2 search_recent_tweets expects max_results between 10 and 100
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

    except Exception as e:
        logger.error(f"[Twitter] Error fetching tweets for {clean_ticker}: {e}")

    logger.info(f"[Twitter] Fetched {len(tweets_text)} tweets for {clean_ticker}")
    return tweets_text


def clean_social_text(text):
    """
    Removes URLs, special characters, and normalizes whitespace in text.
    
    Args:
        text (str): Raw post/tweet text.
        
    Returns:
        str: Cleaned text string.
    """
    if not text:
        return ""
    # Remove URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    # Remove special characters except basic punctuation and alphanumeric spaces
    text = re.sub(r'[^a-zA-Z0-9\s.,!?\'"-]', '', text)
    # Normalize whitespace
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
    removes URLs and special characters, and returns a single clean list of strings
    representing retail chatter.
    
    Args:
        ticker_symbol (str): Stock ticker (e.g., 'CIPLA' or 'CIPLA.NS').
        
    Returns:
        list: Clean list of strings representing the last 24 hours of retail chatter.
    """
    _normalize_ticker(ticker_symbol)  # Validate before calling either connector.
    logger.info(f"[SocialScraper] Starting social sentiment ingestion for ticker: {ticker_symbol}")
    
    reddit_posts = get_reddit_posts(ticker_symbol)
    tweets = get_tweets(ticker_symbol)

    raw_combined = reddit_posts + tweets
    clean_list = []

    for raw in raw_combined:
        cleaned = clean_social_text(raw)
        if len(cleaned) > 10:  # Filter out empty or negligible string snippets
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
