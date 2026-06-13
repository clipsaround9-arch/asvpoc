import os
import time
import threading
from flask import Flask, render_template_string
from playwright.async_api import async_playwright
import asyncio

app = Flask(__name__)

TARGET_URL = "https://web.sensibull.com/option-chain?tradingsymbol=NIFTY&view=greeks&expiry=2026-06-16"

LATEST_MARKET_DATA = {
    "timestamp": "Initializing...",
    "status_message": "System booted. Waiting for the first 5-minute background scrap cycle...",
    "rows": []
}

async def extract_sensibull_chain():
    global LATEST_MARKET_DATA
    current_time = time.strftime('%Y-%m-%d %H:%M:%S IST')
    print(f"[{current_time}] Background thread trigger initiated...")
    LATEST_MARKET_DATA["status_message"] = "Scraper active. Spawning Chromium session..."
    
    async with async_playwright() as p:
        # CRITICAL FOR CLOUD DEPLOYMENTS: Launch with sandbox bypass arguments
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        try:
            LATEST_MARKET_DATA["status_message"] = f"Navigating to Sensibull at {time.strftime('%H:%M:%S')}..."
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
            
            LATEST_MARKET_DATA["status_message"] = "Waiting for table elements to render..."
            await page.wait_for_selector("text=Strike", timeout=25000)
            await asyncio.sleep(5)  # Let dynamic option text finish syncing
            
            raw_rows = await page.locator("div[class*='OptionChainRow'], tr").all_inner_texts()
            
            cleaned_rows = []
            for row_text in raw_rows:
                columns = [col.strip() for col in row_text.split("\n") if col.strip()]
                if columns and not any(x in columns[0] for x in ["Call LTP", "Open Interest", "Charts"]):
                    cleaned_rows.append(columns)
            
            if cleaned_rows:
                LATEST_MARKET_DATA["timestamp"] = time.strftime('%Y-%m-%d %H:%M:%S IST')
                LATEST_MARKET_DATA["status_message"] = "Data stream steady."
                LATEST_MARKET_DATA["rows"] = cleaned_rows
                print(f"[{time.strftime('%H:%M:%S')}] Success! {len(cleaned_rows)} rows saved to memory.")
            else:
                LATEST_MARKET_DATA["status_message"] = "Failed to parse text. Table structure layout mismatch."
                
        except Exception as e:
            error_msg = str(e).split('\n')[0] # Get first line of error
            LATEST_MARKET_DATA["status_message"] = f"Scraper Error: {error_msg}"
            print(f"Error during extraction: {str(e)}")
        finally:
            await browser.close()

def run_async_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Run once immediately on server boot instead of waiting 5 minutes
    try:
        loop.run_until_complete(extract_sensibull_chain())
    except Exception as e:
        print(f"Initial run error: {e}")
        
    while True:
        time.sleep(300) # Wait 5 minutes between cycles
        try:
            loop.run_until_complete(extract_sensibull_chain())
        except Exception as e:
            print(f"Loop error: {e}")

# Start background tracking worker
threading.Thread(target=run_async_loop, daemon=True).start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Live Sensibull Dashboard</title>
    <meta http-equiv="refresh" content="15"> <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; background-color: #f7fafc; color: #2d3748; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; border-left: 4px solid #3182ce; }
        h2 { margin-top: 0; color: #2b6cb0; }
        .status-box { font-size: 14px; padding: 10px; background: #ebf8ff; border: 1px solid #bee3f8; color: #2b6cb0; border-radius: 4px; display: inline-block; }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        th, td { padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: left; }
        th { background: #2b6cb0; color: white; text-transform: uppercase; font-size: 11px; letter-spacing: 1px; }
        tr:hover { background: #f7fafc; }
        .no-data { text-align: center; padding: 30px; color: #a0aec0; font-style: italic; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Sensibull NIFTY Option Chain Tape Engine</h2>
        <p><strong>Last Checked:</strong> {{ data.timestamp }}</p>
        <div class="status-box"><strong>Engine Status:</strong> {{ data.status_message }}</div>
    </div>
    
    <table>
        <thead>
            <tr>
                <th>Scraped Data Rows Matrix</th>
            </tr>
        </thead>
        <tbody>
            {% if data.rows %}
                {% for row in data.rows %}
                <tr>
                    <td><strong>{{ " | ".join(row) }}</strong></td>
                </tr>
                {% endfor %}
            {% else %}
                <tr>
                    <td class="no-data">Waiting for scraper loop to complete data handshake... Page auto-refresh active.</td>
                </tr>
            {% endif %}
        </tbody>
    </table>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(HTML_TEMPLATE, data=LATEST_MARKET_DATA)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
