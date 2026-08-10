import pytest
from unittest.mock import patch, MagicMock
from gemini_analyzer import GeminiSentimentAnalyzer

def test_fetch_daily_bias_success():
    with patch("gemini_analyzer.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Simulate structured output JSON text returned from Gemini
        mock_response = MagicMock()
        mock_response.text = '{"summary": "A positive test summary.", "sentiment_score": 0.75}'
        mock_client.models.generate_content.return_value = mock_response
        
        analyzer = GeminiSentimentAnalyzer()
        score = analyzer.fetch_daily_bias("Test Company", ["Headline 1", "Headline 2"])
        
        assert score == 0.75

def test_fetch_daily_bias_empty():
    with patch("gemini_analyzer.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        analyzer = GeminiSentimentAnalyzer()
        score = analyzer.fetch_daily_bias("Test Company", [])
        
        assert score == 0.0

def test_fetch_daily_bias_failure():
    with patch("gemini_analyzer.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Simulate API Exception
        mock_client.models.generate_content.side_effect = Exception("API error")
        
        analyzer = GeminiSentimentAnalyzer()
        score = analyzer.fetch_daily_bias("Test Company", ["Headline 1"])
        
        assert score == 0.0
