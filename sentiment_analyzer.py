from transformers import pipeline

class FinBERTSentimentAnalyzer:
    """Agent responsible for analyzing financial news sentiment using ProsusAI/finbert."""
    
    def __init__(self):
        # Initialize text-classification pipeline with finbert model
        self.analyzer = pipeline('text-classification', model='ProsusAI/finbert')
        
    def score_headlines(self, headlines_list):
        """Iterates through headlines list, analyzes them using FinBERT, and returns average sentiment float.
        
        Args:
            headlines_list (list): List of headlines as strings.
            
        Returns:
            float: Unified sentiment average score between -1.0 and 1.0.
        """
        if not headlines_list:
            return 0.0
            
        total_score = 0.0
        count = 0
        
        # Pass to analyzer
        for headline in headlines_list:
            if not headline or not isinstance(headline, str):
                continue
                
            try:
                # pipeline returns a list of dicts, e.g. [{'label': 'positive', 'score': 0.95}]
                result = self.analyzer(headline)
                if result:
                    res = result[0]
                    label = res.get('label', '').lower()
                    score = float(res.get('score', 0.0))
                    
                    if label == 'positive':
                        total_score += score
                    elif label == 'negative':
                        total_score -= score
                    elif label == 'neutral':
                        total_score += 0.0
                        
                    count += 1
            except Exception as e:
                print(f"[FinBERT Analyzer Error] Error scoring headline: {e}")
                
        if count == 0:
            return 0.0
            
        return total_score / count
