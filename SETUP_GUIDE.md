# Step-by-Step Setup Guide

Follow these steps exactly to get your Lighter.xyz Trading Bot running.

---

## Step 1: Create Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Enter a name for your bot (e.g., "My Lighter Trading Bot")
4. Enter a username for your bot (must end with `bot`, e.g., `my_lighter_trading_bot`)
5. **Copy the API token** that BotFather gives you (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)
6. Save this token - you'll need it later

---

## Step 2: Get Your Telegram User ID

1. Open Telegram and search for **@userinfobot**
2. Start the bot and send any message
3. It will reply with your user ID (a number like `123456789`)
4. **Copy this ID** - you'll need it for security

---

## Step 3: Setup Project Files

In your VS Code project folder, create these files:

### File 1: `requirements.txt`
Create a new file named `requirements.txt` and paste:

```
python-telegram-bot==20.7
python-dotenv==1.0.0
aiohttp==3.9.1
web3==6.11.3
eth-account==0.10.0
asyncio==3.4.3
```

### File 2: `.env`
Create a new file named `.env` (just `.env`, no other name) and paste:

```
TELEGRAM_BOT_TOKEN=paste_your_bot_token_here
LIGHTER_PRIVATE_KEY=paste_your_wallet_private_key_here
LIGHTER_API_KEY=
LIGHTER_NETWORK=mainnet
ALLOWED_USER_IDS=paste_your_telegram_user_id_here
```

**Replace the values:**
- `paste_your_bot_token_here` → Your token from Step 1
- `paste_your_wallet_private_key_here` → Your wallet private key (from MetaMask or other wallet)
- `paste_your_telegram_user_id_here` → Your ID from Step 2

### File 3: `config.py`
Create `config.py` and paste the entire config code from the repository.

### File 4: `lighter_client.py`
Create `lighter_client.py` and paste the entire lighter client code from the repository.

### File 5: `bot.py`
Create `bot.py` and paste the entire bot code from the repository.

---

## Step 4: Install Python (if not installed)

### Windows:
1. Go to https://www.python.org/downloads/
2. Download Python 3.11 or later
3. **IMPORTANT**: Check "Add Python to PATH" during installation
4. Click Install

### Mac:
```bash
brew install python
```

### Linux (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

---

## Step 5: Open Terminal in VS Code

1. In VS Code, press `` Ctrl + ` `` (backtick) to open terminal
2. Or go to **View → Terminal**

---

## Step 6: Create Virtual Environment

In the terminal, run these commands one by one:

### Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

### Mac/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` at the start of your terminal line.

---

## Step 7: Install Dependencies

With the virtual environment activated, run:

```bash
pip install -r requirements.txt
```

Wait for all packages to install (may take 1-2 minutes).

---

## Step 8: Get Your Wallet Private Key

### From MetaMask:
1. Open MetaMask
2. Click the 3 dots menu → Account Details
3. Click "Show Private Key"
4. Enter your password
5. **Copy the private key** (starts with 0x...)
6. Paste it in your `.env` file

**WARNING**: Never share your private key with anyone!

---

## Step 9: Fund Your Lighter.xyz Account

1. Go to https://app.lighter.xyz
2. Connect your wallet
3. Deposit USDC to your trading account
4. Make sure you have enough for your planned trades

---

## Step 10: Run the Bot

In VS Code terminal (with venv activated), run:

```bash
python bot.py
```

You should see:
```
INFO - Starting bot...
INFO - Lighter client initialized on mainnet
INFO - Bot initialized successfully!
```

---

## Step 11: Test Your Bot

1. Open Telegram
2. Find your bot (search for the username you created)
3. Click **Start** or send `/start`
4. You should see the welcome message
5. Try `/trade` to start a trading setup

---

## Using the Bot

### Start a Trade:
1. Send `/trade`
2. Select first asset (BTC, ETH, or SOL)
3. Choose LONG or SHORT
4. Enter margin (e.g., `100` for $100)
5. Enter leverage (e.g., `10` for 10x)
6. Repeat for second asset
7. Enter profit target (e.g., `50` for $50)
8. Confirm to start trading

### Check Status:
Send `/status` to see current PnL

### Emergency Stop:
Send `/panic` to close all positions immediately

### Stop Trading:
Send `/stop` to stop monitoring and close positions

---

## Troubleshooting

### "TELEGRAM_BOT_TOKEN not set"
- Make sure your `.env` file is in the same folder as `bot.py`
- Check that the token is correct (no extra spaces)

### "You are not authorized"
- Add your Telegram user ID to `ALLOWED_USER_IDS` in `.env`
- Make sure there are no spaces around the ID

### "ModuleNotFoundError"
- Make sure virtual environment is activated (you see `(venv)`)
- Run `pip install -r requirements.txt` again

### Bot not responding
- Check the terminal for error messages
- Make sure the bot is running (no crashes)
- Try restarting with `python bot.py`

---

## Folder Structure

Your project folder should look like this:

```
your-project-folder/
├── venv/                 (created automatically)
├── .env                  (your secrets - DO NOT SHARE)
├── bot.py
├── config.py
├── lighter_client.py
└── requirements.txt
```

---

## Quick Command Reference

| Action | Command |
|--------|---------|
| Activate venv (Windows) | `venv\Scripts\activate` |
| Activate venv (Mac/Linux) | `source venv/bin/activate` |
| Install packages | `pip install -r requirements.txt` |
| Run bot | `python bot.py` |
| Stop bot | Press `Ctrl + C` in terminal |

---

## Security Tips

1. **Never share your `.env` file** - it contains your private key
2. **Add `.env` to `.gitignore`** if using git
3. **Only add your own Telegram ID** to ALLOWED_USER_IDS
4. **Test with small amounts** first
5. **Use testnet** for testing (change LIGHTER_NETWORK to testnet)

---

## Need Help?

If you get stuck:
1. Check the error message in the terminal
2. Make sure all files are saved
3. Make sure virtual environment is activated
4. Double-check your `.env` values
