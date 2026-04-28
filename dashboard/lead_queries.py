import pandas as pd
from typing import Any

def fetch_top_leads(client: Any, min_score: int = 50, limit: int = 100) -> pd.DataFrame:
    """
    Fetches the highest-scoring leads from the retailrocket dataset.
    Scores are based on: View=1, AddToCart=20, Transaction=100.
    """
    query = """
    SELECT 
        visitor_id,
        countIf(event_type = 'view') AS views,
        countIf(event_type = 'addtocart') AS add_to_carts,
        countIf(event_type = 'transaction') AS purchases,
        (views * 1) + (add_to_carts * 20) + (purchases * 100) AS lead_score,
        (add_to_carts > 0 AND purchases = 0) AS cart_abandoned
    FROM retailrocket_raw.events
    GROUP BY visitor_id
    HAVING lead_score >= {min_score}
    ORDER BY lead_score DESC
    LIMIT {limit}
    """
    
    parameters = {
        "min_score": min_score,
        "limit": limit
    }
    
    # client.query_df will substitute standard python string formatting if passed as parameters?
    # Actually, clickhouse_connect supports named parameters using %(name)s. Let's use standard f-strings for simple int substitution.
    
    formatted_query = f"""
    SELECT 
        visitor_id,
        countIf(event_type = 'view') AS views,
        countIf(event_type = 'addtocart') AS add_to_carts,
        countIf(event_type = 'transaction') AS purchases,
        toUInt32((views * 1) + (add_to_carts * 20) + (purchases * 100)) AS lead_score,
        toUInt8(add_to_carts > 0 AND purchases = 0) AS cart_abandoned
    FROM retailrocket_raw.events
    GROUP BY visitor_id
    HAVING lead_score >= {int(min_score)}
    ORDER BY lead_score DESC
    LIMIT {int(limit)}
    """
    
    df = client.query_df(formatted_query)
    
    if df.empty:
        return pd.DataFrame(columns=[
            "visitor_id", "views", "add_to_carts", "purchases", "lead_score", "cart_abandoned"
        ])
        
    return df

def fetch_lead_summary(client: Any, min_score: int = 50) -> dict:
    """
    Fetches high-level metrics for the lead identification dashboard.
    """
    query = f"""
    SELECT 
        uniq(visitor_id) AS total_visitors,
        countIf(lead_score >= {int(min_score)}) AS qualified_leads,
        countIf(cart_abandoned > 0 AND purchases = 0) AS total_abandoners
    FROM (
        SELECT 
            visitor_id,
            countIf(event_type = 'addtocart') AS add_to_carts,
            countIf(event_type = 'transaction') AS purchases,
            (countIf(event_type = 'view') * 1) + (add_to_carts * 20) + (purchases * 100) AS lead_score,
            (add_to_carts > 0 AND purchases = 0) AS cart_abandoned
        FROM retailrocket_raw.events
        GROUP BY visitor_id
    )
    """
    
    df = client.query_df(query)
    if df.empty:
        return {
            "total_visitors": 0,
            "qualified_leads": 0,
            "total_abandoners": 0
        }
        
    row = df.iloc[0]
    return {
        "total_visitors": int(row["total_visitors"]),
        "qualified_leads": int(row["qualified_leads"]),
        "total_abandoners": int(row["total_abandoners"])
    }
