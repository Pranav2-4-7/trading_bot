import pytest
from unittest.mock import patch, MagicMock
from social_scraper import get_reddit_posts, get_tweets, clean_social_text, get_social_text

def test_clean_social_text():
    raw_text = "Check out $CIPLA at https://example.com/chart! Great upside 🚀🚀 #bullish"
    cleaned = clean_social_text(raw_text)
    assert "https://" not in cleaned
    assert "example.com" not in cleaned
    assert "CIPLA" in cleaned
    assert "Great upside" in cleaned

def test_get_reddit_posts_missing_credentials(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    posts = get_reddit_posts("CIPLA.NS")
    assert posts == []

def test_get_reddit_posts_mocked(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "dummy_id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "dummy_secret")
    
    mock_post1 = MagicMock()
    mock_post1.title = "CIPLA earnings breakout"
    mock_post1.selftext = "Solid quarterly results for CIPLA stock."
    
    mock_subreddit = MagicMock()
    mock_subreddit.search.return_value = [mock_post1]
    
    mock_reddit_instance = MagicMock()
    mock_reddit_instance.subreddit.return_value = mock_subreddit
    
    with patch("social_scraper.praw.Reddit", return_value=mock_reddit_instance):
        posts = get_reddit_posts("CIPLA", limit=10)
        assert len(posts) == 3  # 1 post per subreddit * 3 subreddits
        assert "CIPLA earnings breakout Solid quarterly results for CIPLA stock." in posts[0]

def test_get_tweets_missing_token(monkeypatch):
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
    tweets = get_tweets("CIPLA.NS")
    assert tweets == []

def test_get_tweets_mocked(monkeypatch):
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "dummy_bearer")
    
    mock_tweet1 = MagicMock()
    mock_tweet1.text = "Buying $CIPLA on the dip today! https://t.co/xyz123"
    
    mock_response = MagicMock()
    mock_response.data = [mock_tweet1]
    
    mock_client = MagicMock()
    mock_client.search_recent_tweets.return_value = mock_response
    
    with patch("social_scraper.tweepy.Client", return_value=mock_client):
        tweets = get_tweets("CIPLA", max_results=20)
        assert len(tweets) == 1
        assert tweets[0] == "Buying $CIPLA on the dip today! https://t.co/xyz123"

def test_get_social_text_aggregation(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "dummy_id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "dummy_secret")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "dummy_bearer")
    
    with patch("social_scraper.get_reddit_posts", return_value=["CIPLA target 1600 http://link.com!"]), \
         patch("social_scraper.get_tweets", return_value=["$CIPLA bullish pattern breakout #nifty"]):
        
        result = get_social_text("CIPLA.NS")
        assert len(result) == 2
        assert "CIPLA target 1600" in result[0]
        assert "http" not in result[0]
        assert "CIPLA bullish pattern breakout nifty" in result[1]
