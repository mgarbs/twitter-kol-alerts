# Twitter Monitor

A Python script to monitor Twitter accounts for new tweets in real-time.

## Setup

1. Install requirements:
```bash
pip install -r requirements.txt
```

2. Create a .env file with your Twitter API token:
```
TWITTER_BEARER_TOKEN=your_token_here
```

3. Run the script:
```bash
python twitter_monitor.py
```

## Configuration

Edit the following variables at the top of the script:
- CHECK_INTERVAL_MINS: How often to check for new tweets
- LOOKBACK_MINS: How far back to look for tweets
- HANDLES: List of Twitter handles to monitor
