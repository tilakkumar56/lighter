#!/usr/bin/env python3
"""
Lighter.xyz Account Index Finder

This script helps you find your Lighter account index.
You need this to enable REAL trading on the bot.

Usage:
    python find_account_index.py YOUR_WALLET_ADDRESS

Example:
    python find_account_index.py 0x1234567890abcdef1234567890abcdef12345678
"""

import asyncio
import sys
import aiohttp


async def find_account_index(wallet_address: str, network: str = "mainnet"):
    """
    Find Lighter account index by wallet address
    
    Args:
        wallet_address: Your Ethereum wallet address (L1 address)
        network: 'mainnet' or 'testnet'
    """
    base_url = (
        "https://mainnet.zklighter.elliot.ai"
        if network == "mainnet"
        else "https://testnet.zklighter.elliot.ai"
    )
    
    print(f"\n🔍 Looking up account for: {wallet_address}")
    print(f"📡 Network: {network}")
    print(f"🌐 API URL: {base_url}\n")
    
    async with aiohttp.ClientSession() as session:
        # Method 1: Try the account endpoint with L1 address
        try:
            url = f"{base_url}/api/v1/account"
            params = {"l1_address": wallet_address}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract account index
                    account_index = data.get("account_index") or data.get("index")
                    
                    if account_index is not None:
                        print("=" * 50)
                        print(f"✅ FOUND YOUR ACCOUNT!")
                        print("=" * 50)
                        print(f"\n📌 Account Index: {account_index}")
                        print(f"\nAdd this to your .env file:")
                        print(f"   LIGHTER_ACCOUNT_INDEX={account_index}")
                        print("=" * 50)
                        return account_index
                    else:
                        print(f"Response: {data}")
                        
                elif response.status == 404:
                    print("❌ Account not found on this network.")
                    print("\nPossible reasons:")
                    print("  1. You haven't created an account on Lighter yet")
                    print("  2. Wrong wallet address")
                    print("  3. Try the other network (mainnet/testnet)")
                    print("\n📝 To create an account:")
                    print("  1. Go to https://app.lighter.xyz")
                    print("  2. Connect your wallet")
                    print("  3. Create an account and deposit funds")
                else:
                    text = await response.text()
                    print(f"API response ({response.status}): {text}")
                    
        except Exception as e:
            print(f"Error: {e}")
        
        # Method 2: Try accounts_by_l1_address endpoint
        try:
            url = f"{base_url}/api/v1/accounts_by_l1_address"
            params = {"l1_address": wallet_address}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list) and len(data) > 0:
                        print("\n📋 Found accounts:")
                        for i, account in enumerate(data):
                            idx = account.get("account_index") or account.get("index")
                            is_master = account.get("is_master", True)
                            acc_type = "Master" if is_master else "Sub-account"
                            print(f"  {i+1}. Account Index: {idx} ({acc_type})")
                        
                        # Use master account
                        master = next((a for a in data if a.get("is_master", True)), data[0])
                        account_index = master.get("account_index") or master.get("index")
                        
                        print(f"\n📌 Use this in your .env:")
                        print(f"   LIGHTER_ACCOUNT_INDEX={account_index}")
                        return account_index
                        
        except Exception as e:
            pass
            
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n⚠️  Please provide your wallet address!")
        print("\nExample:")
        print("    python find_account_index.py 0xYourWalletAddress")
        print("\nAlternatively, find it manually:")
        print("    1. Go to https://app.lighter.xyz")
        print("    2. Connect your wallet")
        print("    3. Go to Settings -> API Keys")
        print("    4. Your account index should be shown there")
        sys.exit(1)
    
    wallet_address = sys.argv[1]
    network = sys.argv[2] if len(sys.argv) > 2 else "mainnet"
    
    # Validate wallet address format
    if not wallet_address.startswith("0x") or len(wallet_address) != 42:
        print(f"⚠️  Invalid wallet address format: {wallet_address}")
        print("   Expected format: 0x followed by 40 hex characters")
        sys.exit(1)
    
    asyncio.run(find_account_index(wallet_address, network))


if __name__ == "__main__":
    main()
