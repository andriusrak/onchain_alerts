"""This script scrapes Solana addresses from DexScreener Url and saves them to a JSON file.
Chromedriver update might be be required."""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
import time
from datetime import datetime
import sys
import os
import signal
import json
from threading import Thread
import logging

# Set the URL - this one is specifically filtered
SCRAPE_URL = 'https://dexscreener.com/?rankBy=trendingScoreH24&order=desc&chainIds=solana&dexIds=raydium,orca,meteora&minLiq=10000&minFdv=50000&maxFdv=10000000&minAge=1&maxAge=150&max24HTxns=60000&min6HTxns=50&max5MTxns=1000&min6HVol=20000&min1HChg=1&min5MChg=2'

class DexScreenerScraper:
    def __init__(self):
        self.driver = None
        self.is_running = True
        self.results_file = "solana_addresses.json"
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        print("\nReceived shutdown signal. Cleaning up...")
        self.is_running = False
        self.cleanup()
        sys.exit(0)

    def setup_driver(self):
        try:
            # Set up logging
            logging.basicConfig(level=logging.INFO)
            logger = logging.getLogger(__name__)
            options = uc.ChromeOptions()
            #options.add_argument("--headless")
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--no-first-run')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            if self.driver is not None:
                self.cleanup()

            self.driver = uc.Chrome(options=options)
            return True
        except Exception as e:
            self.log_error(f"Error setting up driver: {str(e)}")
            return False

    def save_results(self, addresses):
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = {
                "timestamp": current_time,
                "addresses": addresses
            }
            
            # Read existing data
            existing_data = []
            if os.path.exists(self.results_file):
                with open(self.results_file, 'r') as f:
                    existing_data = json.load(f)
            
            # Append new data
            existing_data.append(data)
            
            # Write back to file
            with open(self.results_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
                
        except Exception as e:
            self.log_error(f"Error saving results: {str(e)}")

    def log_error(self, message):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("scraper_error.log", "a") as f:
            f.write(f"[{current_time}] {message}\n")

    def scrape_solana_addresses(self, url=SCRAPE_URL):
        max_retries = 3
        current_retry = 0
        
        while current_retry < max_retries and self.is_running:
            try:
                if not self.driver:
                    if not self.setup_driver():
                        return []
                
                self.driver.get(url)
                time.sleep(8)
                
                rows = WebDriverWait(self.driver, 30).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "ds-dex-table-row"))
                )
                
                addresses = []
                for row in rows:
                    if not self.is_running:
                        break
                    try:
                        href = row.get_attribute("href")
                        if href and "/solana/" in href:
                            address = href.split("/solana/")[1]
                            addresses.append(address)
                    except Exception as e:
                        self.log_error(f"Error processing row: {str(e)}")
                        continue
                
                return addresses
                
            except WebDriverException as e:
                self.log_error(f"WebDriver error occurred: {str(e)}")
                current_retry += 1
                self.cleanup()
                time.sleep(5)
            except Exception as e:
                self.log_error(f"Unexpected error: {str(e)}")
                current_retry += 1
                self.cleanup()
                time.sleep(5)
        
        return []

    def continuous_scrape(self, interval_minutes=5):
        while self.is_running:
            try:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if not self.driver and not self.setup_driver():
                    time.sleep(60)
                    continue
                
                addresses = self.scrape_solana_addresses()
                
                if addresses:
                    self.save_results(addresses)
                    print(f"[{current_time}] Scraping complete. Found {len(addresses)} addresses.")
                else:
                    print(f"[{current_time}] Scraping complete. No new addresses found.")
                
                if self.is_running:
                    for _ in range(interval_minutes * 60):
                        if not self.is_running:
                            break
                        time.sleep(1)
                
            except Exception as e:
                self.log_error(f"Error in continuous scrape: {str(e)}")
                self.cleanup()
                time.sleep(60)

    def cleanup(self):
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception as e:
            self.log_error(f"Error during cleanup: {str(e)}")
        finally:
            self.driver = None

def run_scraper_background():
    scraper = DexScreenerScraper()
    thread = Thread(target=scraper.continuous_scrape, daemon=True)
    thread.start()
    return scraper

def main():
    print("Starting DexScreener scraper in background...")
    scraper = run_scraper_background()
    
    print("\nScraper is running in the background.")
    print(f"Results are being saved to '{scraper.results_file}'")
    print("Errors are being logged to 'scraper_error.log'")
    print("\nTo stop the scraper, press Ctrl+C")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping scraper...")
        scraper.is_running = False
        scraper.cleanup()

if __name__ == "__main__":
    main()