"""Combine GDELT news sentiment and retail social sentiment."""

from news_ingestor import GlobalNewsIngestor
from sentiment_analyzer import FinBERTSentimentAnalyzer
from social_scraper import get_social_text


news_ingestor = GlobalNewsIngestor()
_sentiment_analyzer = None


def _get_sentiment_analyzer():
    """Create the shared FinBERT analyzer only when a score is requested."""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = FinBERTSentimentAnalyzer()
    return _sentiment_analyzer


def calculate_retail_sentiment(ticker_symbol):
    """Return the mean label score for recent Reddit and X posts.

    Each positive post contributes +1, each negative post -1, and each
    neutral post 0. An empty feed or failed individual classification has a
    neutral contribution.
    """
    social_texts = get_social_text(ticker_symbol)
    if not social_texts:
        return 0.0

    analyzer = _get_sentiment_analyzer().analyzer
    label_scores = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
    scores = []

    for text in social_texts:
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            result = analyzer(text)
            if result:
                label = str(result[0].get("label", "neutral")).lower()
                scores.append(label_scores.get(label, 0.0))
        except Exception as exc:
            print(f"[Retail Sentiment Error] Could not classify social text: {exc}")

    return sum(scores) / len(scores) if scores else 0.0


def calculate_sentiment(ticker_symbol, company_name=None):
    """Return the GDELT news and retail sentiment scores for a ticker."""
    headlines = news_ingestor.fetch_recent_news(company_name or ticker_symbol, days_back=1)
    news_score = (
        _get_sentiment_analyzer().score_headlines(headlines) if headlines else 0.0
    )
    retail_score = calculate_retail_sentiment(ticker_symbol)
    return {
        "Global_Sentiment": news_score,
        "Retail_Sentiment": retail_score,
    }
