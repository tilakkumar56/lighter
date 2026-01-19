# Lighter.xyz Perpetual Futures Trading Telegram Bot

A Telegram bot for managing dual perpetual futures positions on [Lighter.xyz](https://app.lighter.xyz) with automated profit booking and position reopening.

## Features

- **Real Trading**: Connects to Lighter.xyz Perpetual Futures API via official `lighter-sdk`
- **Dual Trade Setup**: Open two positions simultaneously with different assets
- **Supported Assets**: BTC, ETH, SOL
- **Direction Selection**: Long or Short for each position
- **Custom Parameters**: Set margin amount and leverage for each trade
- **Profit Target**: Set a combined profit target in USD
- **Auto Profit Booking**: Automatically closes positions when profit target is reached
- **Auto Reopen**: Reopens positions with the same setup 50 seconds after booking profit
- **Real-Time Prices**: WebSocket connection to Lighter.xyz for live perpetual futures prices
- **Paper Trading Mode**: Runs in simulation mode if API credentials are not configured

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and see welcome message |
| `/trade` | Start a new dual trade setup |
| `/status` | Check current PnL and position details |
| `/panic` | Emergency close all positions (market sell) |
| `/stop` | Stop monitoring and close all positions |
| `/help` | Show help message |

## Trade Setup Flow

1. **Trade 1 Setup**
   - Select asset (BTC, ETH, or SOL)
   - Choose direction (Long or Short)
   - Enter margin amount in USD
   - Enter leverage (1x - 100x)

2. **Trade 2 Setup**
   - Select asset (BTC, ETH, or SOL)
   - Choose direction (Long or Short)
   - Enter margin amount in USD
   - Enter leverage (1x - 100x)

3. **Set Profit Target**
   - Enter combined profit target in USD

4. **Confirm & Execute**
   - Review the setup summary
   - Confirm to open both positions

5. **Automated Monitoring**
   - Bot monitors PnL every 5 seconds
   - When profit target is reached:
     - Closes all positions
     - Notifies you with profit amount
     - Waits 50 seconds
     - Reopens positions with same setup
   - Loop continues until you use `/stop`

## Installation

### Prerequisites

- Python 3.10 or higher
- A Telegram Bot Token (get from [@BotFather](https://t.me/botfather))
- Lighter.xyz account with funds deposited
- Lighter.xyz API Key (for real trading)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd lighter-trading-bot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Find your Lighter Account Index**
   ```bash
   python find_account_index.py YOUR_WALLET_ADDRESS
   ```
   
   Example:
   ```bash
   python find_account_index.py 0x742d35Cc6634C0532925a3b844Bc9e7595f1E321
   ```
   
   Note the account index that is returned.

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and fill in your credentials:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   LIGHTER_API_KEY_INDEX=3
   LIGHTER_API_PRIVATE_KEY=your_api_private_key_from_lighter
   LIGHTER_ACCOUNT_INDEX=your_account_index_from_step_4
   LIGHTER_NETWORK=mainnet
   ALLOWED_USER_IDS=your_telegram_user_id
   ```

6. **Run the bot**
   ```bash
   python bot.py
   ```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from BotFather | Yes |
| `LIGHTER_API_KEY_INDEX` | API key index (3-254, get from Lighter) | Yes (for real trading) |
| `LIGHTER_API_PRIVATE_KEY` | API private key (generated from Lighter) | Yes (for real trading) |
| `LIGHTER_ACCOUNT_INDEX` | Your account index on Lighter | Yes (for real trading) |
| `LIGHTER_NETWORK` | Network to use: `mainnet` or `testnet` | No (default: mainnet) |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs allowed to use the bot | No |

### Getting Lighter.xyz API Credentials

1. Go to https://app.lighter.xyz
2. Connect your wallet
3. Navigate to **Settings** → **API Keys**
4. Click **Create API Key**
5. Choose an index (3-254, recommend 3)
6. Save the **Private Key** - you'll only see it once!
7. Use `find_account_index.py` to get your account index

### Trading Limits (config.py)

- **Minimum Margin**: $1
- **Maximum Margin**: $100,000
- **Minimum Leverage**: 1x
- **Maximum Leverage**: 100x
- **Profit Check Interval**: 5 seconds
- **Reopen Delay**: 50 seconds

## Security

- **User Authorization**: Only users listed in `ALLOWED_USER_IDS` can use the bot
- **API Keys**: API keys can only process withdrawals to your own wallet address
- **Secure Storage**: Keep your `.env` file secure and never share it

## Risk Warning

⚠️ **IMPORTANT**: Trading futures involves significant risk of loss. Leverage amplifies both gains and losses. Only trade with funds you can afford to lose. This bot is provided for educational purposes. Always test on testnet first.

## Project Structure

```
lighter-trading-bot/
├── bot.py                  # Main Telegram bot logic
├── lighter_client.py       # Lighter.xyz Perps API client
├── config.py               # Configuration settings
├── find_account_index.py   # Helper to find your account index
├── requirements.txt        # Python dependencies
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore rules
├── SETUP_GUIDE.md          # Detailed setup instructions
└── README.md               # This file
```

## Trading Modes

### 🟢 REAL TRADING Mode
When all API credentials are correctly configured:
```
INFO - 🟢 Lighter SDK initialized - REAL TRADING enabled!
INFO - Lighter client initialized | 🟢 REAL TRADING | mainnet
```

### 🟡 PAPER TRADING Mode
When API credentials are missing or invalid:
```
INFO - Lighter client initialized | 🟡 PAPER TRADING | mainnet
```

Paper trading mode uses real Lighter.xyz perpetual futures prices but doesn't execute actual trades.

## Usage Example

1. Start a conversation with your bot on Telegram
2. Send `/trade` to begin
3. Select **BTC** for the first trade
4. Choose **LONG** direction
5. Enter **100** for $100 margin
6. Enter **10** for 10x leverage
7. Select **ETH** for the second trade
8. Choose **SHORT** direction
9. Enter **100** for $100 margin
10. Enter **10** for 10x leverage
11. Enter **50** for $50 profit target
12. Confirm the setup
13. Bot opens both positions and starts monitoring
14. When combined profit reaches $50, bot books profit and notifies you
15. After 50 seconds, bot reopens the same positions
16. Use `/stop` to end the session

## Troubleshooting

### "invalid account index" Error
- Run `python find_account_index.py YOUR_WALLET_ADDRESS`
- Update `LIGHTER_ACCOUNT_INDEX` in your `.env` file with the correct value

### "module 'lighter' has no attribute 'SignerClient'"
- Conflicting packages. Run:
  ```bash
  pip uninstall lighter-v2-python lighter-sdk -y
  pip cache purge
  pip install lighter-sdk
  ```

### Bot shows PAPER TRADING when you expect REAL TRADING
- Verify all API credentials in `.env` are correct
- Make sure `LIGHTER_ACCOUNT_INDEX` is your actual account index (not 0)
- Check that you've created an API key on Lighter.xyz

### Bot not responding
- Check if `TELEGRAM_BOT_TOKEN` is correct
- Ensure the bot is running without errors
- Check if your user ID is in `ALLOWED_USER_IDS`

### Positions not opening
- Verify your Lighter.xyz account has sufficient funds
- Check API credentials are correct
- Ensure you're connected to the correct network

## License

MIT License - See LICENSE file for details.

## Disclaimer

This software is provided "as is" without warranty of any kind. The developers are not responsible for any financial losses incurred through the use of this bot. Always do your own research and trade responsibly.
