"""
Configuration settings for the Lighter.xyz Trading Bot
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = [int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()]

# Lighter.xyz Configuration
LIGHTER_PRIVATE_KEY = os.getenv("LIGHTER_PRIVATE_KEY")
LIGHTER_API_KEY = os.getenv("LIGHTER_API_KEY")
LIGHTER_NETWORK = os.getenv("LIGHTER_NETWORK", "mainnet")

# Supported Assets
SUPPORTED_ASSETS = ["BTC", "ETH", "SOL"]

# Asset to Market ID mapping for Lighter.xyz
# These IDs may need to be updated based on actual Lighter.xyz market IDs
ASSET_MARKET_IDS = {
    "BTC": 0,  # BTC-USD perpetual
    "ETH": 1,  # ETH-USD perpetual
    "SOL": 2,  # SOL-USD perpetual
}

# Trading Configuration
MAX_LEVERAGE = 100
MIN_LEVERAGE = 1
MIN_MARGIN = 1  # Minimum margin in USD
MAX_MARGIN = 100000  # Maximum margin in USD

# Monitoring Configuration
PROFIT_CHECK_INTERVAL = 5  # Check profit every 5 seconds
REOPEN_DELAY = 50  # Wait 50 seconds before reopening positions

# Conversation States
(
    SELECTING_ASSET_1,
    SELECTING_DIRECTION_1,
    ENTERING_MARGIN_1,
    ENTERING_LEVERAGE_1,
    SELECTING_ASSET_2,
    SELECTING_DIRECTION_2,
    ENTERING_MARGIN_2,
    ENTERING_LEVERAGE_2,
    ENTERING_PROFIT_TARGET,
    CONFIRMING_SETUP,
) = range(10)
