import requests
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import telegram
from telegram.error import TelegramError
import asyncio

# Configure logging
logging.basicConfig(
    filename='twitter_telegram_monitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables
load_dotenv()
BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Initialize Telegram bot
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ====== CONFIGURATION ======
# Time windows (all in minutes)
CHECK_INTERVAL_MINS = 1  # How often to check for new tweets
LOOKBACK_MINS = 1    # How far back to look for tweets
MAX_TWEETS_PER_CHECK = 10  # Maximum tweets to fetch per check

# Twitter handles to monitor
HANDLES = [
    'Ashcryptoreal',
    'RealRossU',
    'ZssBecker',
    'JacobKinge',
    'chooserich',
    'LadyofCrypto1',
    'notthreadguy',
    'inversebrah',
    'cobie',
    'CryptoKaleo',
    'CryptoCapo_',
    'TheCrowtrade',
    'Pentosh1',
    'TheCryptoDog',
    'stoolpresidente',
    'moonpay',
    'JakeGagain'
]

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 15  # Twitter's limit
RATE_LIMIT_WINDOW = 15 * 60  # 15 minutes in seconds

# Convert minutes to seconds for internal use
CHECK_INTERVAL = CHECK_INTERVAL_MINS * 60

async def send_telegram_message(message):
    """Send message to Telegram channel"""
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=message,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    except TelegramError as e:
        logging.error(f"Telegram error: {e}")
        print(f"❌ Telegram error: {e}")

def get_user_ids(usernames):
    """Get Twitter user IDs from usernames in a single batch request"""
    headers = {'Authorization': f'Bearer {BEARER_TOKEN}'}
    usernames_str = ','.join(usernames)

    response = requests.get(
        f'https://api.twitter.com/2/users/by?usernames={usernames_str}',
        headers=headers
    )
    if response.status_code != 200:
        raise Exception(f"Failed to get user IDs: {response.text}")

    return {user['username'].lower(): user['id']
            for user in response.json()['data']}

def get_latest_tweets_batch(user_ids, debug=False):
    """Get latest tweet from each user in a single request"""
    if debug:
        print("\n🔍 Debug Information:")
    headers = {'Authorization': f'Bearer {BEARER_TOKEN}'}
    url = 'https://api.twitter.com/2/tweets/search/recent'

    # Format time for lookback window
    lookback_time = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINS)
    formatted_time = lookback_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Build query for all users
    user_queries = ' OR '.join(f'from:{uid}' for uid in user_ids)

    params = {
        'query': f'({user_queries})',
        'max_results': MAX_TWEETS_PER_CHECK,
        'tweet.fields': 'created_at,author_id',
        'start_time': formatted_time
    }

    if debug:
        print(f"🔍 API Query: {params['query']}")
        print(f"🔍 Start Time: {formatted_time}")

    response = requests.get(url, headers=headers, params=params)

    if debug:
        print(f"🔍 Response Status: {response.status_code}")
        print(f"🔍 Response Headers: {dict(response.headers)}")
        print(f"🔍 Full Response: {response.text}\n")

    if response.status_code == 429:
        raise Exception("Rate limit exceeded")
    elif response.status_code != 200:
        raise Exception(f"Failed to get tweets: {response.text}")

    data = response.json()
    if debug and 'meta' in data:
        print(f"🔍 Result Count: {data['meta'].get('result_count', 0)}")

    return data.get('data', [])

async def monitor_tweets(debug_first_check=False):
    """Monitor tweets and send alerts to Telegram"""
    start_msg = "Twitter Monitor Starting"
    print(f"\n🐦 {start_msg}")
    await send_telegram_message("🐦 Twitter Monitor Bot Started\n\n" + 
                              f"Monitoring handles:\n{', '.join(HANDLES)}")

    logging.info(f"{start_msg}. Monitoring handles: {', '.join(HANDLES)}")

    # Get user IDs once at startup
    user_map = get_user_ids(HANDLES)
    user_ids = list(user_map.values())
    id_to_username = {v: k for k, v in user_map.items()}

    seen_tweets = set()
    requests_made = 0
    window_start_time = time.time()

    while True:
        try:
            current_time = time.time()

            # Reset counter if 15 minutes have passed
            if current_time - window_start_time >= RATE_LIMIT_WINDOW:
                requests_made = 0
                window_start_time = current_time

            # Only proceed if we haven't hit rate limit
            if requests_made < RATE_LIMIT_REQUESTS:
                tweets = get_latest_tweets_batch(user_ids, debug=debug_first_check)
                if debug_first_check:
                    debug_first_check = False
                requests_made += 1

                # Log the check timestamp
                check_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if not tweets:
                    no_tweets_msg = f"No new tweets found at {check_time}"
                    logging.info(no_tweets_msg)
                    print(f"\n📭 {no_tweets_msg}\n")
                else:
                    found_msg = f"Found {len(tweets)} new tweet(s) at {check_time}"
                    logging.info(found_msg)
                    print(f"\n📬 {found_msg}")

                for tweet in tweets:
                    if tweet['id'] not in seen_tweets:
                        seen_tweets.add(tweet['id'])
                        tweet_url = f"https://twitter.com/i/web/status/{tweet['id']}"
                        username = id_to_username[tweet['author_id']]
                        
                        # Format message for Telegram
                        message = (f"🔔 New Tweet from @{username}!\n\n"
                                 f"📝 {tweet['text']}\n\n"
                                 f"🔗 {tweet_url}")
                        
                        await send_telegram_message(message)
                        logging.info(f"Sent alert for tweet {tweet['id']} to Telegram")

                # Keep set size manageable
                if len(seen_tweets) > 1000:
                    seen_tweets.clear()

            # Print waiting message with rate limit info
            for i in range(CHECK_INTERVAL, 0, -1):
                remaining_time = int(window_start_time + RATE_LIMIT_WINDOW - time.time())
                if remaining_time > 0:
                    print(f"\r⏳ Next check in {i}s | Rate limit: {requests_made}/{RATE_LIMIT_REQUESTS} requests (resets in {remaining_time}s)", end='', flush=True)
                else:
                    print(f"\r⏳ Next check in {i}s | Rate limit: {requests_made}/{RATE_LIMIT_REQUESTS} requests", end='', flush=True)
                await asyncio.sleep(1)
            print("\r" + " " * 100 + "\r", end='', flush=True)

        except Exception as e:
            error_msg = f"Error: {e}"
            logging.error(error_msg)
            await send_telegram_message(f"❌ {error_msg}")
            
            if "rate limit" in str(e).lower():
                wait_time = int(window_start_time + RATE_LIMIT_WINDOW - time.time())
                if wait_time > 0:
                    print(f"Rate limit hit. Waiting {wait_time} seconds for reset...")
                    await asyncio.sleep(wait_time)
                requests_made = 0
                window_start_time = time.time()
            else:
                await asyncio.sleep(CHECK_INTERVAL)

async def verify_setup():
    """Verify API access and Telegram setup"""
    print("\n🔍 Verifying Setup...")

    try:
        # Test Twitter API
        headers = {'Authorization': f'Bearer {BEARER_TOKEN}'}
        test_response = requests.get(
            'https://api.twitter.com/2/tweets/search/recent?query=from:twitter', 
            headers=headers
        )
        twitter_ok = test_response.status_code == 200
        print(f"✓ Twitter API: {twitter_ok}")
        print(f"✓ Rate Limit Remaining: {test_response.headers.get('x-rate-limit-remaining', 'unknown')}")

        # Get and verify user IDs
        user_map = get_user_ids(HANDLES)
        print("\n✓ Found User IDs:")
        for handle, uid in user_map.items():
            print(f"  - @{handle}: {uid}")

        # Test Telegram
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text="🔍 Bot setup verification test message"
        )
        print("✓ Telegram Bot: Working")

        return twitter_ok

    except Exception as e:
        print(f"\n❌ Setup Verification Failed: {e}")
        return False

async def main():
    print("🚀 Twitter Monitor Telegram Bot")
    print("------------------------------")

    # Verify handles are set
    if not HANDLES or HANDLES[0] == 'handle1':
        print("❌ Please set your Twitter handles in the HANDLES list first!")
        return

    # Verify environment variables
    if not all([BEARER_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID]):
        print("❌ Please set all required environment variables in .env file!")
        return

    # Verify setup
    if not await verify_setup():
        print("\n❌ Please check your configuration and try again.")
        return

    # Ask if user wants debug mode
    debug_mode = input("\nEnable debug mode for first check? (y/n): ").lower() == 'y'

    try:
        await monitor_tweets(debug_mode)
    except KeyboardInterrupt:
        await send_telegram_message("👋 Bot shutting down...")
        print("\n\n👋 Shutting down...")
    except Exception as e:
        error_msg = f"Fatal error: {e}"
        logging.error(error_msg)
        await send_telegram_message(f"❌ {error_msg}")
        print(f"\n❌ {error_msg}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())