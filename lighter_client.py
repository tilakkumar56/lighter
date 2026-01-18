"""
Lighter.xyz API Client for trading operations
Integrates with Lighter.xyz DEX on Arbitrum
"""

import asyncio
import logging
import hmac
import hashlib
import time
import json
from typing import Optional, Dict, Any, List
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import aiohttp

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    LONG = "buy"
    SHORT = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass
class Position:
    """Represents a trading position"""
    market_id: int
    asset: str
    side: str  # LONG or SHORT
    size: Decimal
    entry_price: Decimal
    margin: Decimal
    leverage: int
    unrealized_pnl: Decimal
    liquidation_price: Decimal
    order_id: str = ""


@dataclass
class TradeSetup:
    """Represents a trade setup for one leg"""
    asset: str
    direction: str  # LONG or SHORT
    margin: float
    leverage: int
    market_id: int = 0


@dataclass
class DualTradeSetup:
    """Represents the complete dual trade setup"""
    trade1: TradeSetup
    trade2: TradeSetup
    profit_target: float  # Combined profit target in USD


class LighterClient:
    """
    Client for interacting with Lighter.xyz DEX
    
    Lighter.xyz API Documentation: https://docs.lighter.xyz
    """
    
    # Lighter.xyz API endpoints
    MAINNET_API = "https://mainnet.zklighter.elliot.ai"
    TESTNET_API = "https://testnet.zklighter.elliot.ai"
    
    # Alternative endpoints
    MAINNET_API_V2 = "https://api.lighter.xyz/api/v1"
    
    # Market symbols mapping
    MARKET_SYMBOLS = {
        "BTC": "BTC-USDC",
        "ETH": "ETH-USDC", 
        "SOL": "SOL-USDC",
    }
    
    # Market IDs (these should match Lighter.xyz's actual market IDs)
    MARKET_IDS = {
        "BTC": 1,
        "ETH": 2,
        "SOL": 3,
    }

    def __init__(self, private_key: str, api_key: str = None, network: str = "mainnet"):
        """
        Initialize the Lighter client
        
        Args:
            private_key: Wallet private key for signing transactions
            api_key: API key for authenticated endpoints
            network: 'mainnet' or 'testnet'
        """
        self.private_key = private_key
        self.api_key = api_key
        self.network = network
        self.base_url = self.MAINNET_API if network == "mainnet" else self.TESTNET_API
        self.session: Optional[aiohttp.ClientSession] = None
        self._positions: Dict[str, Position] = {}  # key: asset symbol
        self._markets: Dict[str, Dict] = {}
        self._last_prices: Dict[str, Decimal] = {}
        
    async def initialize(self):
        """Initialize the client and fetch market data"""
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Try to fetch real market data
        await self._fetch_prices()
        logger.info(f"Lighter client initialized on {self.network}")
        
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()
    
    async def _fetch_prices(self):
        """Fetch current prices from price APIs"""
        # Use CoinGecko or similar for real prices
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": "bitcoin,ethereum,solana",
                "vs_currencies": "usd"
            }
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self._last_prices["BTC"] = Decimal(str(data.get("bitcoin", {}).get("usd", 0)))
                    self._last_prices["ETH"] = Decimal(str(data.get("ethereum", {}).get("usd", 0)))
                    self._last_prices["SOL"] = Decimal(str(data.get("solana", {}).get("usd", 0)))
                    logger.info(f"Fetched prices: BTC=${self._last_prices.get('BTC')}, ETH=${self._last_prices.get('ETH')}, SOL=${self._last_prices.get('SOL')}")
                    return
        except Exception as e:
            logger.warning(f"Failed to fetch from CoinGecko: {e}")
        
        # Fallback to Binance
        try:
            for asset, symbol in [("BTC", "BTCUSDT"), ("ETH", "ETHUSDT"), ("SOL", "SOLUSDT")]:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._last_prices[asset] = Decimal(str(data.get("price", 0)))
            logger.info(f"Fetched prices from Binance")
        except Exception as e:
            logger.warning(f"Failed to fetch from Binance: {e}")
            # Use hardcoded fallback only if all else fails
            self._last_prices = {
                "BTC": Decimal("97000"),
                "ETH": Decimal("3300"),
                "SOL": Decimal("200"),
            }
    
    async def get_market_price(self, asset: str) -> Optional[Decimal]:
        """Get the current market price for an asset"""
        # Refresh prices
        await self._fetch_prices()
        return self._last_prices.get(asset)
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get current prices for all supported assets"""
        await self._fetch_prices()
        return self._last_prices.copy()
    
    async def _call_lighter_api(self, endpoint: str, method: str = "GET", data: dict = None) -> Optional[dict]:
        """Make authenticated API call to Lighter.xyz"""
        try:
            url = f"{self.base_url}{endpoint}"
            headers = {
                "Content-Type": "application/json",
            }
            
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            if method == "GET":
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"API error: {response.status} - {await response.text()}")
            else:
                async with self.session.post(url, headers=headers, json=data) as response:
                    if response.status in [200, 201]:
                        return await response.json()
                    else:
                        logger.error(f"API error: {response.status} - {await response.text()}")
        except Exception as e:
            logger.error(f"API call failed: {e}")
        return None
    
    async def open_position(
        self,
        market_id: int,
        side: OrderSide,
        margin: float,
        leverage: int,
        asset: str
    ) -> Optional[Position]:
        """
        Open a new position on Lighter.xyz
        
        For now, this tracks positions locally and monitors real prices.
        Full integration requires Lighter.xyz API credentials and on-chain signing.
        """
        try:
            # Get current market price
            price = await self.get_market_price(asset)
            if not price or price == 0:
                logger.error(f"Could not get price for {asset}")
                return None
            
            # Calculate position size based on margin and leverage
            notional_value = Decimal(str(margin)) * Decimal(str(leverage))
            size = notional_value / price
            
            # Calculate liquidation price (simplified - actual calculation depends on exchange)
            margin_ratio = Decimal("1") / Decimal(str(leverage))
            if side == OrderSide.LONG:
                # Liquidation when price drops by (margin/position_value)
                liquidation_price = price * (1 - margin_ratio * Decimal("0.9"))
            else:
                # Liquidation when price rises by (margin/position_value)
                liquidation_price = price * (1 + margin_ratio * Decimal("0.9"))
            
            # Create position object
            position = Position(
                market_id=market_id,
                asset=asset,
                side=side.name,
                size=size,
                entry_price=price,
                margin=Decimal(str(margin)),
                leverage=leverage,
                unrealized_pnl=Decimal("0"),
                liquidation_price=liquidation_price,
                order_id=f"{asset}_{side.name}_{int(time.time())}"
            )
            
            # Store position by asset
            self._positions[asset] = position
            
            logger.info(f"Position opened: {asset} {side.name} | Entry: ${price:,.2f} | Size: {size:.6f} | Margin: ${margin} | Leverage: {leverage}x")
            
            return position
            
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return None
    
    async def close_position(self, asset: str) -> Optional[Dict[str, Any]]:
        """Close an existing position"""
        try:
            position = self._positions.get(asset)
            if not position:
                logger.warning(f"No position found for {asset}")
                return None
            
            # Get current market price
            current_price = await self.get_market_price(asset)
            if not current_price:
                logger.error(f"Could not get current price for {asset}")
                return None
            
            # Calculate realized PnL
            if position.side == "LONG":
                pnl = (current_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - current_price) * position.size
            
            result = {
                "asset": position.asset,
                "side": position.side,
                "entry_price": float(position.entry_price),
                "exit_price": float(current_price),
                "size": float(position.size),
                "realized_pnl": float(pnl),
                "margin_returned": float(position.margin),
                "leverage": position.leverage,
            }
            
            # Remove the position
            del self._positions[asset]
            
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            logger.info(f"Position closed: {asset} {position.side} | Exit: ${current_price:,.2f} | PnL: {pnl_str}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return None
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all open positions"""
        results = []
        assets = list(self._positions.keys())
        
        for asset in assets:
            result = await self.close_position(asset)
            if result:
                results.append(result)
        
        return results
    
    async def get_position(self, asset: str) -> Optional[Position]:
        """Get a specific position"""
        return self._positions.get(asset)
    
    async def get_all_positions(self) -> List[Position]:
        """Get all open positions"""
        return list(self._positions.values())
    
    async def update_positions_pnl(self) -> Dict[str, Any]:
        """
        Update PnL for all positions using real market prices
        """
        # Refresh prices first
        await self._fetch_prices()
        
        total_pnl = Decimal("0")
        position_details = []
        
        for asset, position in self._positions.items():
            current_price = self._last_prices.get(asset)
            
            if not current_price:
                continue
            
            # Calculate unrealized PnL
            if position.side == "LONG":
                pnl = (current_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - current_price) * position.size
            
            position.unrealized_pnl = pnl
            total_pnl += pnl
            
            pnl_percent = (pnl / position.margin) * 100 if position.margin > 0 else Decimal("0")
            
            position_details.append({
                "asset": position.asset,
                "side": position.side,
                "entry_price": float(position.entry_price),
                "current_price": float(current_price),
                "size": float(position.size),
                "margin": float(position.margin),
                "leverage": position.leverage,
                "unrealized_pnl": float(pnl),
                "pnl_percent": float(pnl_percent),
            })
        
        return {
            "positions": position_details,
            "total_unrealized_pnl": float(total_pnl),
        }
    
    def has_open_positions(self) -> bool:
        """Check if there are any open positions"""
        return len(self._positions) > 0
    
    async def get_account_balance(self) -> Optional[Decimal]:
        """Get account balance (placeholder for actual API call)"""
        return Decimal("10000.00")
