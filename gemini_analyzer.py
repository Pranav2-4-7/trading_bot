import os
import json
from google import genai
from pydantic import BaseModel, Field

class CompanySentiment(BaseModel):
    summary: str = Field(description="A brief 1-sentence explanation of the news sentiment.")
    sentiment_score: float = Field(description="A sentiment classification rating between -1.0 (extremely bearish) and 1.0 (extremely bullish).")

class GeminiSentimentAnalyzer:
    """Agent responsible for analyzing deep fundamental financial news sentiment using Gemini 2.5 Flash."""
    
    def __init__(self):
        # Load API key from environment
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()

    def fetch_daily_bias(self, company_name, headlines_list):
        """Sends headlines to Gemini 2.5 Flash and returns structured sentiment float.
        
        Args:
            company_name (str): Readable name of company.
            headlines_list (list): List of news headlines.
            
        Returns:
            float: Sentiment score from -1.0 to 1.0.
        """
        if not headlines_list:
            return 0.0
            
        headlines_joined = "\n".join(f"- {h}" for h in headlines_list)
        prompt = (
            f"Perform a deep financial news sentiment analysis for the company: '{company_name}'.\n"
            f"Analyze the following list of headlines collected over the past 24 hours:\n"
            f"{headlines_joined}\n\n"
            f"Evaluate if the news is bullish, bearish, or neutral, and provide a unified sentiment score "
            f"between -1.0 (very negative/bearish) and 1.0 (very positive/bullish)."
        )
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=dict(
                    response_mime_type="application/json",
                    response_schema=CompanySentiment
                )
            )
            
            if response.text:
                data = json.loads(response.text)
                score = float(data.get("sentiment_score", 0.0))
                return max(-1.0, min(score, 1.0))
                
        except Exception as e:
            print(f"[Gemini Analyzer Error] Failed to generate sentiment bias for {company_name}: {e}")
            
        return 0.0
