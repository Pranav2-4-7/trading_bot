import pytest
from unittest.mock import patch, MagicMock
from sentiment_analyzer import FinBERTSentimentAnalyzer

def test_score_headlines_positive():
    # Mock pipeline and analyzer
    with patch("sentiment_analyzer.pipeline") as mock_pipeline:
        mock_analyzer = MagicMock()
        mock_pipeline.return_value = mock_analyzer
        
        # Simulate positive prediction
        mock_analyzer.return_value = [{'label': 'positive', 'score': 0.85}]
        
        analyzer = FinBERTSentimentAnalyzer()
        score = analyzer.score_headlines(["Good news for the company"])
        
        assert score == 0.85

def test_score_headlines_negative():
    with patch("sentiment_analyzer.pipeline") as mock_pipeline:
        mock_analyzer = MagicMock()
        mock_pipeline.return_value = mock_analyzer
        
        # Simulate negative prediction
        mock_analyzer.return_value = [{'label': 'negative', 'score': 0.90}]
        
        analyzer = FinBERTSentimentAnalyzer()
        score = analyzer.score_headlines(["Earnings dropped dramatically"])
        
        assert score == -0.90

def test_score_headlines_neutral():
    with patch("sentiment_analyzer.pipeline") as mock_pipeline:
        mock_analyzer = MagicMock()
        mock_pipeline.return_value = mock_analyzer
        
        # Simulate neutral prediction
        mock_analyzer.return_value = [{'label': 'neutral', 'score': 0.70}]
        
        analyzer = FinBERTSentimentAnalyzer()
        score = analyzer.score_headlines(["Today is Monday"])
        
        assert score == 0.0

def test_score_headlines_empty():
    with patch("sentiment_analyzer.pipeline") as mock_pipeline:
        mock_analyzer = MagicMock()
        mock_pipeline.return_value = mock_analyzer
        
        analyzer = FinBERTSentimentAnalyzer()
        score = analyzer.score_headlines([])
        
        assert score == 0.0

def test_score_headlines_average():
    with patch("sentiment_analyzer.pipeline") as mock_pipeline:
        mock_analyzer = MagicMock()
        mock_pipeline.return_value = mock_analyzer
        
        # Mock successive predictions: positive 0.8, negative 0.4
        mock_analyzer.side_effect = [
            [{'label': 'positive', 'score': 0.80}],
            [{'label': 'negative', 'score': 0.40}]
        ]
        
        analyzer = FinBERTSentimentAnalyzer()
        score = analyzer.score_headlines(["Positive story", "Negative story"])
        
        # Average of 0.8 and -0.4 is 0.2
        assert abs(score - 0.2) < 1e-5
