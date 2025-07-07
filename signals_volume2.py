"This script analyzes Solana tokens candles using DexScreener(Token data) and GeckoTerminal (OHLCV 5-min candles) APIs."

import json
from time import sleep
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from collections import deque
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, calls_per_minute):
        self.calls_per_minute = calls_per_minute
        self.interval = 60.0 / calls_per_minute
        self.timestamps = deque()

    def wait_if_needed(self):
        current_time = datetime.now().timestamp()
        
        while self.timestamps and current_time - self.timestamps[0] > 60:
            self.timestamps.popleft()
        
        if len(self.timestamps) >= self.calls_per_minute:
            wait_time = 60 - (current_time - self.timestamps[0])
            if wait_time > 0:
                sleep(wait_time)
        
        self.timestamps.append(current_time)

class PatternDetector:
    def __init__(self):
        pass

    def prepare_data(self, ohlcv_data: List[List[float]]) -> pd.DataFrame:
        """Prepare DataFrame with OHLCV data, excluding the last row(candle) if it is still open."""
        df = pd.DataFrame(
            ohlcv_data,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'],
        )
        # Exclude the last row if the candle is still open
        if self.is_candle_closed(df.iloc[-1]):
            return df
        else:
            return df.iloc[:-1]


    def analyze_candles(self, ohlcv_data: List[List[float]]) -> Dict:
        """Analyze candle data to check if the most recent closed candle has higher volume than average of previous closed candles."""
        df = self.prepare_data(ohlcv_data)
        
        # Reverse the DataFrame to process the most recent candle first
        df = df.iloc[::-1]
        
        # Find the first closed candle
        for i, row in df.iterrows():
            if self.is_candle_closed(row):
                break
        else:
            return {'valid': False, 'reason': 'insufficient_candles'}

        # Check if we have at least 3 closed candles.
        #if i < 2:
        #    return {'valid': False, 'reason': 'less_than_3_closed_candles'}    
        
        # Calculate the average volume of previous closed candles
        #avg_volume = df.loc[:i, 'volume'].mean()
        #avg_volume = df.loc[:i, 'volume'].median()

        # Calculate the weighted average volume of previous closed candles
        # Giving more weight to the most recent and oldest data points
        # weights = np.linspace(1, 0.1, len(df.loc[:i, 'volume']))
        # ema = df.loc[:i, 'volume'].ewm(span=10, adjust=False).mean()
        # avg_volume = (df.loc[:i, 'volume'] * weights).sum() / weights.sum()

        # Calculate the triangular weighted average of the previous closed candle volumes
        # prev_volumes = df.loc[:i, 'volume']
        # weights = np.linspace(1, 0, len(prev_volumes))
        # avg_volume = (prev_volumes * weights).sum() / weights.sum() #triangular weighted avg
        # Calculate the harmonic mean of the previous closed candle volumes
        #prev_volumes = df.loc[:i, 'volume']
        #avg_volume = len(prev_volumes) / (1 / prev_volumes).sum()

        # Calculate the geometric mean of the previous closed candle volumes
        prev_volumes = df.loc[:i, 'volume']
        avg_volume = prev_volumes.prod() ** (1 / len(prev_volumes))

        if avg_volume < 10:
            return {'valid': False, 'reason': 'gay ass coin'}

        last_candle_volume = df.iloc[i]['volume']
        
        effective_avg_volume = avg_volume if avg_volume >= 999 else avg_volume * 7

        # Check if the last candle's volume is greater than the average volume
        if last_candle_volume > effective_avg_volume:
            return {
                'valid': True,
                'timestamp': df.iloc[i]['timestamp'],
                'last_candle_volume': last_candle_volume,
                'average_previous_volume': avg_volume
            }
        
        return {'valid': False, 'reason': 'last_candle_volume_not_higher_than_average'}

    def is_candle_closed(self, candle: pd.Series) -> bool:
        """Check if a candle is closed by verifying if its timestamp aligns with a closed 5-minute interval."""
        # The current time in seconds
        current_time = datetime.now().timestamp()
        
        # Candle timestamp should be a multiple of 300 seconds (5 minutes) for it to be closed
        if candle['timestamp'] % 300 == 0 and candle['timestamp'] < current_time:
            return True
        return False

    def alert_pattern(self, pair_data: Dict, pattern_results: Dict) -> None:
        """Log alert for detected pattern."""
        alert_msg = f"""
Name: {pair_data['name']}
Token: {pair_data['symbol']}
Last Candle Volume: {pattern_results['last_candle_volume']}
Average Previous Volume: {pattern_results['average_previous_volume']}
Current Price: ${pair_data['price']:.6f}
24h Volume: ${pair_data['volume_24h']:,.2f}
Liquidity: ${pair_data['liquidity']:,.2f}
FDV: ${pair_data['fdv']:,.0f}
Trade URL: {pair_data['url']}
X Sentiment: https://x.com/search?q=%24{pair_data['symbol']}+OR+{pair_data['CA']}
X General: https://x.com/search?q={pair_data['name'].replace(" ", "+")}
        """
        logger.info(alert_msg)
        
        with open('pattern_alerts.txt', 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}\n{alert_msg}\n{'='*50}\n")


class MarketDataProcessor:
    def __init__(self, dex_rate_limit: int = 60, ohlcv_rate_limit: int = 30):
        self.detector = PatternDetector()
        self.dex_limiter = RateLimiter(calls_per_minute=dex_rate_limit)
        self.ohlcv_limiter = RateLimiter(calls_per_minute=ohlcv_rate_limit)

    def load_latest_addresses(self) -> List[str]:
        """Load addresses from JSON file"""
        try:
            with open('solana_addresses.json', 'r') as file:
                data = json.load(file)
                if data and len(data) > 0:
                    return data[0]['addresses']
        except (FileNotFoundError, json.JSONDecodeError, IndexError) as e:
            logger.error(f"Error loading addresses: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error loading addresses: {str(e)}")
            return []

    def process_addresses(self):
        while True:
            try:
                addresses = self.load_latest_addresses()
                if not addresses:
                    logger.warning("No addresses found to process")
                    sleep(300)
                    continue

                logger.info(f"Starting new cycle with {len(addresses)} addresses")
                dex_data_queue = []

                # First pass: Get all DexScreener data
                for address in addresses:
                    try:
                        self.dex_limiter.wait_if_needed()
                        dex_response = requests.get(
                            f'https://api.dexscreener.com/latest/dex/pairs/solana/{address}',
                            headers={},
                            timeout=10
                        )
                        dex_response.raise_for_status()
                        dex_data = dex_response.json()
                        
                        if 'pairs' in dex_data and len(dex_data['pairs']) > 0:
                            pair = dex_data['pair']
                            fdv = float(pair['fdv'])
                            liquidity = float(pair['liquidity']['usd'])
                            
                            #Skip address if liquidity is greater than FDV
                            if liquidity > fdv*0.8:
                               continue
                            
                            dex_data_queue.append({
                                'address': address,
                                'data': dex_data
                            })
                    except requests.exceptions.RequestException as e:
                        logger.error(f"DexScreener API request failed for address {address}: {str(e)}")
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected error processing DexScreener data for {address}: {str(e)}")
                        continue

                # Second pass: Process OHLCV data
                for item in dex_data_queue:
                    try:
                        dex_data = item['data']
                        address = item['address']
                        
                        pool_address = dex_data['pairs'][0]['pairAddress']
                        pair = dex_data['pairs'][0]
                        
                        pair_data = {
                            'symbol': f"{pair['baseToken']['symbol']}",
                            'name': pair['baseToken']['name'],
			    'CA': pair['baseToken']['address'],
                            'price': float(pair['priceUsd']),
                            'liquidity': float(pair['liquidity']['usd']),
                            'volume_24h': float(pair['volume']['h24']),
                            'url': pair['url'],
                            'fdv': float(pair['fdv'])
                        }
                        
                        self.ohlcv_limiter.wait_if_needed()
                        
                        ohlcv_response = requests.get(
                            f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool_address}/ohlcv/minute?aggregate=5",
                            timeout=10
                        )
                        ohlcv_response.raise_for_status()
                        ohlcv_data = ohlcv_response.json()
                        
                        candles = ohlcv_data['data']['attributes']['ohlcv_list']
                        pattern_results = self.detector.analyze_candles(candles)
                        
                        if pattern_results['valid']:
                            self.detector.alert_pattern(pair_data, pattern_results)
                        
                        # Save results
                        result = {
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'address': address,
                            'pool_address': pool_address,
                            'pair_data': pair_data,
                            'pattern_results': pattern_results
                        }
                        
                        with open('analysis_results.json', 'a') as f:
                            json.dump(result, f)
                            f.write('\n')
                    except requests.exceptions.RequestException as e:
                        logger.error(f"OHLCV API request failed for address {address}: {str(e)}")
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected error processing OHLCV data for {address}: {str(e)}")
                        continue
                logger.info(f"Completed cycle at {datetime.now()}. Waiting 5 minutes...")
                #clears solana addresses json after completing cycle

                with open('solana_addresses.json', 'w') as file:
                    json.dump([], file)
                sleep(300)

            except Exception as e:
                logger.error(f"Critical error in main loop: {str(e)}")
                sleep(300)

if __name__ == "__main__":
    processor = MarketDataProcessor()
    processor.process_addresses()