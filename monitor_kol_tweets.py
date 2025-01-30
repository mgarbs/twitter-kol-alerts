import requests
import logging
import os
import time
from datetime import datetime, timedelta, timezone
import subprocess
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    filename='twitter_monitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables
load_dotenv()
BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')

# ====== CONFIGURATION ======
# Time windows (all in minutes)
CHECK_INTERVAL_MINS = 3  # How often to check for new tweets
LOOKBACK_MINS = 3      # How far back to look for tweets
MAX_TWEETS_PER_CHECK = 10  # Maximum tweets to fetch per check

# Twitter handles to monitor
HANDLES = [
    'Ashcryptoreal',
    'lynk0x',
    'AltcoinGordon',
    'RealRossU',
    'ZssBecker',
    'JacobKinge',
    'solana',
    'chooserich'
]

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 15  # Twitter's limit
RATE_LIMIT_WINDOW = 15 * 60  # 15 minutes in seconds

# Convert minutes to seconds for internal use
CHECK_INTERVAL = CHECK_INTERVAL_MINS * 60

def play_notification_sound():
    """Play notification sound on macOS"""
    try:
        if os.path.exists('notification.mp3'):
            subprocess.run(['afplay', 'notification.mp3'])
        else:
            subprocess.run(['afplay', '/System/Library/Sounds/Glass.aiff'])
    except Exception as e:
        logging.error(f"Error playing sound: {e}")

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

def monitor_tweets(debug_first_check=False):
    """Monitor tweets using optimized batch requests"""
    start_msg = "Twitter Monitor Starting"
    print(f"\n🐦 {start_msg}")
    print(f"👥 Monitoring handles: {', '.join(HANDLES)}")
    print(f"⏱️  Checking every {CHECK_INTERVAL_MINS} minutes")
    print(f"🔍 Looking back {LOOKBACK_MINS} minutes for tweets")
    
    # Log startup
    logging.info(f"{start_msg}. Monitoring handles: {', '.join(HANDLES)}")
    
    # Get user IDs once at startup (counts as 1 request)
    user_map = get_user_ids(HANDLES)
    user_ids = list(user_map.values())
    
    # Create reverse mapping for displaying usernames
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
                    debug_first_check = False  # Only debug first check
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
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Log and print the new tweet
                        log_message = f"New tweet from @{username} at {timestamp}: {tweet['text']}\nURL: {tweet_url}"
                        logging.info(log_message)
                        print(f"\n🔔 New Tweet from @{username}!")
                        print(f"📝 {tweet['text']}")
                        print(f"🔗 {tweet_url}\n")
                        
                        # Play notification sound
                        play_notification_sound()
                
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
                time.sleep(1)
            print("\r" + " " * 100 + "\r", end='', flush=True)
            
        except Exception as e:
            logging.error(f"Error: {e}")
            print(f"\n❌ Error: {e}")
            if "rate limit" in str(e).lower():
                # Wait until the rate limit window resets
                wait_time = int(window_start_time + RATE_LIMIT_WINDOW - time.time())
                if wait_time > 0:
                    print(f"Rate limit hit. Waiting {wait_time} seconds for reset...")
                    time.sleep(wait_time)
                requests_made = 0
                window_start_time = time.time()
            else:
                # For other errors, wait one interval
                time.sleep(CHECK_INTERVAL)

def verify_api_access():
    """Test API access and monitor setup"""
    print("\n🔍 Verifying API Access...")
    
    try:
        # Test the bearer token
        headers = {'Authorization': f'Bearer {BEARER_TOKEN}'}
        test_response = requests.get('https://api.twitter.com/2/tweets/search/recent?query=from:twitter', headers=headers)
        
        print(f"✓ API Connection: {test_response.status_code == 200}")
        print(f"✓ Rate Limit Remaining: {test_response.headers.get('x-rate-limit-remaining', 'unknown')}")
        
        # Get and verify user IDs
        user_map = get_user_ids(HANDLES)
        print("\n✓ Found User IDs:")
        for handle, uid in user_map.items():
            print(f"  - @{handle}: {uid}")
            
        return True
            
    except Exception as e:
        print(f"\n❌ API Verification Failed: {e}")
        return False

def main():
    print("🚀 Twitter Monitor")
    print("----------------")
    
    # Verify handles are set
    if not HANDLES or HANDLES[0] == 'handle1':
        print("❌ Please set your Twitter handles in the HANDLES list first!")
        return
        
    # Verify bearer token
    if not BEARER_TOKEN:
        print("❌ Please set your TWITTER_BEARER_TOKEN in .env file!")
        return
    
    # Verify API access first
    if not verify_api_access():
        print("\n❌ Please check your API token and try again.")
        return
        
    # Ask if user wants debug mode
    debug_mode = input("\nEnable debug mode for first check? (y/n): ").lower() == 'y'
    
    try:
        monitor_tweets(debug_mode)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(f"\n❌ Fatal error: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()