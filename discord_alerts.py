""" This script monitors a file for new trading alerts and sends them to a Discord channel using a webhook.
 It avoids sending duplicate alerts by tracking previously sent alerts and periodically cleans up the list of sent alerts."""

import asyncio
import os
import logging
import requests
import time

logging.basicConfig(level=logging.DEBUG)

# Discord Webhook URL (Replace with your actual Discord Webhook URL)
WEBHOOK_URL = ''

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

file_path = "pattern_alerts.txt"

# Track previously sent alerts to avoid duplicates (URL and timestamp)
sent_alerts = set()

# Time limit (6 hours = 21600 seconds). Cleans up sent_alerts every 6 hours
CLEANUP_INTERVAL = 6 * 60 * 60 

async def send_alert_to_discord(alert_msg):
    """Send the alert message to a Discord channel using Webhook."""
    try:
        # Send a POST request to the Discord webhook
        payload = {
            'content': alert_msg  # Message content to be sent to Discord
        }
        response = requests.post(WEBHOOK_URL, json=payload)
        
        # Check for successful response
        if response.status_code == 204:
            print("Alert sent to Discord channel successfully.")
        else:
            print(f"Failed to send alert to Discord. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending alert to Discord: {e}")

async def cleanup_sent_alerts():
    """Periodically clean up the sent_alerts set."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        print(f"Cleaning up sent_alerts. Current size: {len(sent_alerts)}")
        current_time = time.time()
        sent_alerts.clear()
        print(f"Sent alerts cleared. New size: {len(sent_alerts)}")
 
async def monitor_alerts():
    """Monitors pattern_alerts.txt for new alerts."""
    # Start the cleanup task
    cleanup_task = asyncio.create_task(cleanup_sent_alerts())
 
    last_position = 0  # Track the last read position in the file
    while True:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                # Move to the last read position
                f.seek(last_position)
                new_lines = f.readlines()
                # Update position for the next read
                last_position = f.tell()
 
            # Process each new alert found
            alert_block = []
            trade_url = None  # To hold the URL line from the alert block
            for line in new_lines:
                if line.strip() == "==================================================":
                    if alert_block: 
                        # Check if we have a trade URL and whether it has been sent
                        if trade_url and trade_url not in sent_alerts:
                            # Send the full alert (including the URL)
                            full_alert = "".join(alert_block)
                            await send_alert_to_discord(full_alert)
                            sent_alerts.add(trade_url)  # Mark this URL as sent
                            print(f"Alert sent to Discord: {trade_url}")
                        alert_block = []  # Reset for the next alert
                        trade_url = None  # Reset the URL
                else:
                    alert_block.append(line)
                    # Look for the line containing the Trade URL and capture it
                    if line.startswith("Trade URL: https://"):
                        trade_url = line.strip()
 
            # Handle any remaining alert block at the end of the file
            if alert_block and trade_url and trade_url not in sent_alerts:
                full_alert = "\n".join(alert_block)
                await send_alert_to_discord(full_alert)
                sent_alerts.add(trade_url)
                print(f"Alert sent to Discord: {trade_url}")
 
        # Check for new alerts every 10 seconds
        await asyncio.sleep(10)
 
if __name__ == "__main__":
    try:
        asyncio.run(monitor_alerts())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
