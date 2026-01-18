# Lighter.xyz Futures Trading Telegram Bot

A Telegram bot for managing dual futures positions on [Lighter.xyz](https://app.lighter.xyz) with automated profit booking and position reopening.

## Features

- **Dual Trade Setup**: Open two positions simultaneously with different assets
- **Supported Assets**: BTC, ETH, SOL
- **Direction Selection**: Long or Short for each position
- **Custom Parameters**: Set margin amount and leverage for each trade
- **Profit Target**: Set a combined profit target in USD
- **Auto Profit Booking**: Automatically closes positions when profit target is reached
- **Auto Reopen**: Reopens positions with the same setup 50 seconds after booking profit
- **Monitoring Loop**: Continuous monitoring until manually stopped

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

- Python 3.9 or higher
- A Telegram Bot Token (get from [@BotFather](https://t.me/botfather))
- Lighter.xyz account with API access
- Wallet private key with funds on Lighter.xyz

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

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and fill in your credentials:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   LIGHTER_PRIVATE_KEY=your_wallet_private_key
   LIGHTER_API_KEY=your_lighter_api_key
   LIGHTER_NETWORK=mainnet
   ALLOWED_USER_IDS=your_telegram_user_id
   ```

5. **Run the bot**
   ```bash
   python bot.py
   ```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from BotFather | Yes |
| `LIGHTER_PRIVATE_KEY` | Your wallet private key for signing transactions | Yes |
| `LIGHTER_API_KEY` | Lighter.xyz API key (if required) | No |
| `LIGHTER_NETWORK` | Network to use: `mainnet` or `testnet` | No (default: mainnet) |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs allowed to use the bot | No |

### Trading Limits (config.py)

- **Minimum Margin**: $1
- **Maximum Margin**: $100,000
- **Minimum Leverage**: 1x
- **Maximum Leverage**: 100x
- **Profit Check Interval**: 5 seconds
- **Reopen Delay**: 50 seconds

## Security

- **User Authorization**: Only users listed in `ALLOWED_USER_IDS` can use the bot
- **Private Key**: Never share your private key. Store it securely in the `.env` file
- **API Key**: Keep your Lighter.xyz API key secure

## Risk Warning

⚠️ **IMPORTANT**: Trading futures involves significant risk of loss. Leverage amplifies both gains and losses. Only trade with funds you can afford to lose. This bot is provided for educational purposes. Always test on testnet first.

## Project Structure

```
lighter-trading-bot/
├── bot.py              # Main Telegram bot logic
├── lighter_client.py   # Lighter.xyz API client
├── config.py           # Configuration settings
├── requirements.txt    # Python dependencies
├── .env.example        # Example environment variables
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

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

### Bot not responding
- Check if `TELEGRAM_BOT_TOKEN` is correct
- Ensure the bot is running without errors
- Check if your user ID is in `ALLOWED_USER_IDS`

### Positions not opening
- Verify your wallet has sufficient funds
- Check if `LIGHTER_PRIVATE_KEY` is correct
- Ensure you're connected to the correct network

### API errors
- Check your internet connection
- Verify Lighter.xyz API is accessible
- Review error logs for specific issues

## License

MIT License - See LICENSE file for details.

## Disclaimer

This software is provided "as is" without warranty of any kind. The developers are not responsible for any financial losses incurred through the use of this bot. Always do your own research and trade responsibly.
