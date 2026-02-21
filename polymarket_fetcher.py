#!/usr/bin/env python3
"""
===================================
Polymarket Prediction Market Data
===================================

Fetch prediction market data from Polymarket API.
No API key required - public endpoints.

Usage:
    python polymarket_fetcher.py                    # Get trending markets
    python polymarket_fetcher.py --search "Trump"   # Search markets
    python polymarket_fetcher.py --category "Politics"  # Filter by category
"""

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Polymarket API endpoints
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


@dataclass
class Market:
    """Polymarket market data"""
    id: str
    question: str
    description: str
    category: str
    outcomes: List[str]
    outcome_prices: List[float]  # Implied probabilities
    volume: float
    liquidity: float
    end_date: str
    active: bool
    closed: bool
    url: str


class PolymarketClient:
    """Polymarket API client"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_events(self, limit: int = 10, active: bool = True) -> List[dict]:
        """
        Get events/markets from Polymarket
        
        Args:
            limit: Number of events to fetch
            active: Only active markets
            
        Returns:
            List of event dictionaries
        """
        try:
            url = f"{GAMMA_API}/events"
            params = {
                'limit': limit,
                'active': str(active).lower(),
                'closed': 'false',
                'order': 'volume',
                'ascending': 'false'
            }
            
            logger.info(f"Fetching events from Polymarket...")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            events = response.json()
            logger.info(f"Fetched {len(events)} events")
            return events
            
        except Exception as e:
            logger.error(f"Failed to fetch events: {e}")
            return []
    
    def search_markets(self, query: str, limit: int = 10) -> List[dict]:
        """
        Search markets by keyword
        
        Args:
            query: Search query
            limit: Number of results
            
        Returns:
            List of matching markets
        """
        try:
            url = f"{GAMMA_API}/public-search"
            params = {
                'query': query,
                'limit': limit
            }
            
            logger.info(f"Searching for '{query}'...")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            results = response.json()
            markets = results.get('markets', [])
            logger.info(f"Found {len(markets)} markets")
            return markets
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def get_market_by_id(self, market_id: str) -> Optional[dict]:
        """
        Get specific market details
        
        Args:
            market_id: Market ID
            
        Returns:
            Market dictionary or None
        """
        try:
            url = f"{GAMMA_API}/markets/{market_id}"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to get market {market_id}: {e}")
            return None
    
    def parse_market(self, market_data: dict) -> Optional[Market]:
        """
        Parse market data into Market object
        
        Args:
            market_data: Raw market data from API
            
        Returns:
            Market object or None
        """
        try:
            # Parse outcomes and prices
            outcomes_str = market_data.get('outcomes', '[]')
            prices_str = market_data.get('outcomePrices', '[]')
            
            try:
                outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
                prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
                prices = [float(p) for p in prices]
            except:
                outcomes = []
                prices = []
            
            return Market(
                id=market_data.get('id', ''),
                question=market_data.get('question', ''),
                description=market_data.get('description', '')[:200],
                category=market_data.get('category', 'Unknown'),
                outcomes=outcomes,
                outcome_prices=prices,
                volume=float(market_data.get('volumeNum', 0) or 0),
                liquidity=float(market_data.get('liquidityNum', 0) or 0),
                end_date=market_data.get('endDate', ''),
                active=market_data.get('active', False),
                closed=market_data.get('closed', False),
                url=f"https://polymarket.com/market/{market_data.get('slug', '')}"
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse market: {e}")
            return None
    
    def format_market(self, market: Market) -> str:
        """Format market for display"""
        lines = []
        lines.append(f"📊 {market.question}")
        lines.append(f"   Category: {market.category}")
        
        # Show outcomes with probabilities
        if market.outcomes and market.outcome_prices:
            lines.append("   Outcomes:")
            for outcome, price in zip(market.outcomes, market.outcome_prices):
                probability = float(price) * 100
                lines.append(f"     • {outcome}: {probability:.1f}%")
        
        lines.append(f"   Volume: ${market.volume:,.2f}")
        lines.append(f"   Ends: {market.end_date[:10] if market.end_date else 'N/A'}")
        lines.append(f"   🔗 {market.url}")
        
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Polymarket Data Fetcher')
    parser.add_argument('--search', '-s', type=str, help='Search query')
    parser.add_argument('--limit', '-l', type=int, default=10, help='Number of results')
    parser.add_argument('--category', '-c', type=str, help='Filter by category')
    
    args = parser.parse_args()
    
    client = PolymarketClient()
    
    print("\n" + "=" * 80)
    print("📈 Polymarket Prediction Markets")
    print("=" * 80 + "\n")
    
    if args.search:
        # Search mode
        markets_data = client.search_markets(args.search, args.limit)
        print(f"Search results for '{args.search}':\n")
        
        for data in markets_data[:args.limit]:
            market = client.parse_market(data)
            if market:
                print(client.format_market(market))
                print()
                
    else:
        # Get trending markets
        events = client.get_events(args.limit)
        print(f"Top {args.limit} Markets by Volume:\n")
        
        count = 0
        for event in events:
            # Get markets from event
            markets = event.get('markets', [])
            for market_data in markets:
                if args.category and market_data.get('category') != args.category:
                    continue
                    
                market = client.parse_market(market_data)
                if market:
                    print(client.format_market(market))
                    print()
                    count += 1
                    
                    if count >= args.limit:
                        break
            
            if count >= args.limit:
                break
    
    print("=" * 80)


if __name__ == "__main__":
    main()
