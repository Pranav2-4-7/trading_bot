import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from news_ingestor import GlobalNewsIngestor
from gdeltdoc.errors import NotFoundError, ServerError

def test_fetch_recent_news_success():
    ingestor = GlobalNewsIngestor()
    
    # Mock GdeltDoc and article_search
    with patch("news_ingestor.GdeltDoc") as mock_gdelt:
        mock_instance = MagicMock()
        mock_gdelt.return_value = mock_instance
        
        # Create a mock DataFrame with titles
        mock_df = pd.DataFrame({
            "title": ["Article 1", "Article 2", "Article 3"]
        })
        mock_instance.article_search.return_value = mock_df
        
        titles = ingestor.fetch_recent_news("Reliance", days_back=1)
        
        assert len(titles) == 3
        assert titles[0] == "Article 1"
        assert titles[2] == "Article 3"

def test_fetch_recent_news_empty():
    ingestor = GlobalNewsIngestor()
    
    with patch("news_ingestor.GdeltDoc") as mock_gdelt:
        mock_instance = MagicMock()
        mock_gdelt.return_value = mock_instance
        
        # Return empty DataFrame
        mock_instance.article_search.return_value = pd.DataFrame()
        
        titles = ingestor.fetch_recent_news("TCS", days_back=1)
        assert titles == []

def test_fetch_recent_news_error_handling():
    ingestor = GlobalNewsIngestor()
    
    with patch("news_ingestor.GdeltDoc") as mock_gdelt:
        mock_instance = MagicMock()
        mock_gdelt.return_value = mock_instance
        
        # Simulate ServerError
        mock_instance.article_search.side_effect = ServerError("GDELT Server Error")
        
        titles = ingestor.fetch_recent_news("Infosys", days_back=1)
        assert titles == []
