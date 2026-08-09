import datetime
import pandas as pd
from gdeltdoc import GdeltDoc, Filters
from gdeltdoc.errors import NotFoundError, ServerError

class GlobalNewsIngestor:
    """Agent responsible for pulling real-time global news events using the GDELT Doc API."""
    
    def fetch_recent_news(self, company_name, days_back=1):
        """Fetches recent news articles for a company from GDELT.
        
        Args:
            company_name (str): The name/keyword of the company to search for.
            days_back (int): Number of days back to start the search.
            
        Returns:
            list: List of top 10 article titles as strings.
        """
        # Calculate date range
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days_back)
        
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        try:
            # Initialize Filters
            filters = Filters(
                keyword=company_name,
                start_date=start_date_str,
                end_date=end_date_str
            )
            
            # Instantiate GdeltDoc
            gd = GdeltDoc()
            
            # Retrieve search results as a pandas DataFrame
            df = gd.article_search(filters)
            
            # If the DataFrame is empty or None, return an empty list
            if df is None or df.empty or "title" not in df.columns:
                return []
                
            # Extract top 10 article titles
            titles = df["title"].head(10).tolist()
            # Clean and filter out any non-string entries
            return [str(title).strip() for title in titles if pd.notna(title)]
            
        except (NotFoundError, ServerError) as e:
            print(f"[GDELT API Error] Connection or server error when searching for {company_name}: {e}")
            return []
        except Exception as e:
            print(f"[GDELT Error] Unexpected error fetching news for {company_name}: {e}")
            return []
