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
websockets>=12.0.0
lighter-sdk>=1.0.2
```

### File 2: `.env`
Create a new file named `.env` (just `.env`, no other name) and paste:

```
TELEGRAM_BOT_TOKEN=paste_your_bot_token_here
LIGHTER_API_KEY_INDEX=3
LIGHTER_API_PRIVATE_KEY=paste_your_api_private_key_here
LIGHTER_ACCOUNT_INDEX=paste_your_account_index_here
LIGHTER_NETWORK=mainnet
ALLOWED_USER_IDS=paste_your_telegram_user_id_here
```

**Replace the values:**
- `paste_your_bot_token_here` → Your token from Step 1
- `paste_your_api_private_key_here` → Your Lighter API private key (from Step 8)
- `paste_your_account_index_here` → Your account index number (from Step 9)
- `paste_your_telegram_user_id_here` → Your ID from Step 2

### File 3: `config.py`
Create `config.py` and paste the entire config code from the repository.

### File 4: `lighter_client.py`
Create `lighter_client.py` and paste the entire lighter client code from the repository.

### File 5: `bot.py`
Create `bot.py` and paste the entire bot code from the repository.

### File 6: `find_account_index.py`
Create `find_account_index.py` and paste the helper script from the repository.

---

## Step 4: Install Python (if not installed)

### Windows:
1. Go to https://www.python.org/downloads/
2. Download Python 3.10 or later
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

## Step 8: Create Lighter.xyz API Key

1. Go to https://app.lighter.xyz
2. Connect your wallet
3. Go to **Settings** → **API Keys**
4. Click **Create API Key**
5. Choose an API Key Index (3-254, recommend using 3)
6. **Save the Private Key** that is generated - you'll only see this once!
7. Add these to your `.env` file:
   - `LIGHTER_API_KEY_INDEX=3` (or whatever index you chose)
   - `LIGHTER_API_PRIVATE_KEY=your_private_key_here`

---

## Step 9: Find Your Account Index

Your account index is a unique number assigned to your Lighter account. Here's how to find it:

### Method 1: Use the Helper Script
```bash
python find_account_index.py YOUR_WALLET_ADDRESS
```

Replace `YOUR_WALLET_ADDRESS` with your Ethereum wallet address (e.g., `0x1234...`).

### Method 2: Check Lighter Website
1. Go to https://app.lighter.xyz
2. Connect your wallet
3. Your account index may be shown in Settings or can be found in the URL

### Example:
```bash
python find_account_index.py 0x742d35Cc6634C0532925a3b844Bc9e7595f1E321
```

The script will output something like:
```
✅ FOUND YOUR ACCOUNT!
📌 Account Index: 12345

Add this to your .env file:
   LIGHTER_ACCOUNT_INDEX=12345
```

Update your `.env` file with the correct account index.

---

## Step 10: Fund Your Lighter.xyz Account

1. Go to https://app.lighter.xyz
2. Connect your wallet
3. Deposit USDC to your trading account
4. Make sure you have enough for your planned trades

---

## Step 11: Run the Bot

In VS Code terminal (with venv activated), run:

```bash
python bot.py
```

### Success - REAL TRADING Mode:
```
INFO - Starting bot...
INFO - 🟢 Lighter SDK initialized - REAL TRADING enabled!
INFO - Lighter client initialized | 🟢 REAL TRADING | mainnet
INFO - Bot initialized successfully!
```

### Paper Trading Mode (API not configured):
```
INFO - Starting bot...
INFO - Lighter client initialized | 🟡 PAPER TRADING | mainnet
INFO - Bot initialized successfully!
```

If you see PAPER TRADING, check your API credentials in `.env`.

---

## Step 12: Test Your Bot

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

### "invalid account index" Error
- Run `python find_account_index.py YOUR_WALLET_ADDRESS` to find your correct account index
- Update `LIGHTER_ACCOUNT_INDEX` in your `.env` file

### "module 'lighter' has no attribute 'SignerClient'"
- You may have conflicting packages. Run:
```bash
pip uninstall lighter-v2-python lighter-sdk -y
pip cache purge
pip install lighter-sdk
```

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

### Paper Trading Mode when you expect Real Trading
- Check that `LIGHTER_API_PRIVATE_KEY` is set correctly
- Check that `LIGHTER_ACCOUNT_INDEX` is your actual account index (not 0)
- Make sure you've created an API key on Lighter.xyz

---

## Folder Structure

Your project folder should look like this:

```
your-project-folder/
├── venv/                     (created automatically)
├── .env                      (your secrets - DO NOT SHARE)
├── bot.py
├── config.py
├── lighter_client.py
├── find_account_index.py
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
| Find account index | `python find_account_index.py 0xYOUR_WALLET` |

---

## Security Tips

1. **Never share your `.env` file** - it contains your API keys
2. **Add `.env` to `.gitignore`** if using git
3. **Only add your own Telegram ID** to ALLOWED_USER_IDS
4. **Test with small amounts** first
5. **Use testnet** for testing (change LIGHTER_NETWORK to testnet)
6. **API keys can't withdraw** to other addresses (only to your own wallet)

---

## Need Help?

If you get stuck:
1. Check the error message in the terminal
2. Make sure all files are saved
3. Make sure virtual environment is activated
4. Double-check your `.env` values
5. Run `python find_account_index.py YOUR_WALLET` to verify account index
