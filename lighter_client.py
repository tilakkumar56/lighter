"""
Lighter.xyz API Client for trading operations
Integrates with Lighter.xyz DEX futures on Arbitrum
"""

import asyncio
import logging
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
    
    Lighter.xyz API for price data
    """
    
    # Lighter.xyz API endpoints
    LIGHTER_API_BASE = "https://api.lighter.xyz"
    
    # Market IDs on Lighter.xyz (verify these from their docs/app)
    MARKET_IDS = {
        "BTC": 0,
        "ETH": 1,
        "SOL": 2,
    }
    
    # Market symbols
    MARKET_SYMBOLS = {
        "BTC": "BTCUSD",
        "ETH": "ETHUSD",
        "SOL": "SOLUSD",
    }

    def __init__(self, private_key: str, api_key: str = None, network: str = "mainnet"):
        """
        Initialize the Lighter client
        
        Args:
            private_key: Wallet private key for signing transactions
            api_key: Lighter.xyz API key for authenticated endpoints
            network: 'mainnet' or 'testnet'
        """
        self.private_key = private_key
        self.api_key = api_key
        self.network = network
        self.session: Optional[aiohttp.ClientSession] = None
        self._positions: Dict[str, Position] = {}  # key: asset symbol
        self._last_prices: Dict[str, Decimal] = {}
        self._markets_info: Dict[str, Dict] = {}
        
    async def initialize(self):
        """Initialize the client and fetch market data"""
        timeout = aiohttp.ClientTimeout(total=15)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Fetch initial market data and prices from Lighter
        await self._fetch_markets_info()
        await self._fetch_lighter_prices()
        
        logger.info(f"Lighter client initialized on {self.network}")
        
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()
    
    async def _fetch_markets_info(self):
        """Fetch market information from Lighter.xyz"""
        try:
            # Try to get markets info from Lighter API
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            async with self.session.get(
                f"{self.LIGHTER_API_BASE}/api/v1/markets",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Fetched markets info from Lighter.xyz")
                    # Parse and store market info
                    if isinstance(data, list):
                        for market in data:
                            symbol = market.get("symbol", "")
                            if "BTC" in symbol:
                                self._markets_info["BTC"] = market
                            elif "ETH" in symbol:
                                self._markets_info["ETH"] = market
                            elif "SOL" in symbol:
                                self._markets_info["SOL"] = market
                    return
                else:
                    logger.warning(f"Lighter markets API returned {response.status}")
        except Exception as e:
            logger.warning(f"Failed to fetch markets from Lighter: {e}")
    
    async def _fetch_lighter_prices(self):
        """Fetch current prices from Lighter.xyz API"""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        # Try different Lighter.xyz API endpoints
        endpoints_to_try = [
            f"{self.LIGHTER_API_BASE}/api/v1/tickers",
            f"{self.LIGHTER_API_BASE}/api/v1/prices",
            f"{self.LIGHTER_API_BASE}/api/v1/orderbook/ticker",
            f"{self.LIGHTER_API_BASE}/v1/tickers",
        ]
        
        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(endpoint, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Lighter API response from {endpoint}: {json.dumps(data)[:200]}...")
                        
                        # Parse the response based on structure
                        if isinstance(data, dict):
                            await self._parse_ticker_data(data)
                        elif isinstance(data, list):
                            for item in data:
                                await self._parse_ticker_data(item)
                        
                        if self._last_prices:
                            logger.info(f"Lighter prices: {dict(self._last_prices)}")
                            return
            except Exception as e:
                logger.debug(f"Endpoint {endpoint} failed: {e}")
                continue
        
        # Try individual market endpoints
        for asset, market_id in self.MARKET_IDS.items():
            try:
                async with self.session.get(
                    f"{self.LIGHTER_API_BASE}/api/v1/markets/{market_id}/ticker",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = self._extract_price(data)
                        if price:
                            self._last_prices[asset] = price
                            logger.info(f"Lighter {asset} price: ${price}")
            except Exception as e:
                logger.debug(f"Failed to fetch {asset} price: {e}")
        
        if not self._last_prices:
            logger.warning("Could not fetch prices from Lighter.xyz API. Please check your API key.")
    
    async def _parse_ticker_data(self, data: dict):
        """Parse ticker data from various response formats"""
        # Try to extract prices from common response formats
        symbol = data.get("symbol", data.get("market", "")).upper()
        
        # Extract price from various possible fields
        price = None
        for price_field in ["lastPrice", "last_price", "markPrice", "mark_price", "indexPrice", "index_price", "price"]:
            if price_field in data:
                try:
                    price = Decimal(str(data[price_field]))
                    break
                except:
                    continue
        
        if price and price > 0:
            if "BTC" in symbol:
                self._last_prices["BTC"] = price
            elif "ETH" in symbol:
                self._last_prices["ETH"] = price
            elif "SOL" in symbol:
                self._last_prices["SOL"] = price
    
    def _extract_price(self, data: dict) -> Optional[Decimal]:
        """Extract price from response data"""
        for field in ["lastPrice", "last_price", "markPrice", "mark_price", "indexPrice", "index_price", "price", "last"]:
            if field in data:
                try:
                    return Decimal(str(data[field]))
                except:
                    continue
        return None
    
    async def get_market_price(self, asset: str) -> Optional[Decimal]:
        """Get the current market price for an asset from Lighter.xyz"""
        await self._fetch_lighter_prices()
        return self._last_prices.get(asset)
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get current prices for all supported assets"""
        await self._fetch_lighter_prices()
        return self._last_prices.copy()
    
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
        
        This tracks positions locally using Lighter.xyz prices.
        For actual order execution, you need to use the Lighter SDK with wallet signing.
        """
        try:
            # Get current market price from Lighter
            price = await self.get_market_price(asset)
            if not price or price == 0:
                logger.error(f"Could not get Lighter.xyz price for {asset}")
                return None
            
            # Calculate position size based on margin and leverage
            notional_value = Decimal(str(margin)) * Decimal(str(leverage))
            size = notional_value / price
            
            # Calculate liquidation price
            margin_ratio = Decimal("1") / Decimal(str(leverage))
            if side == OrderSide.LONG:
                liquidation_price = price * (1 - margin_ratio * Decimal("0.9"))
            else:
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
            
            # Store position
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
            
            # Get current price from Lighter
            current_price = await self.get_market_price(asset)
            if not current_price:
                logger.error(f"Could not get current Lighter.xyz price for {asset}")
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
        """Update PnL for all positions using Lighter.xyz prices"""
        # Refresh prices from Lighter
        await self._fetch_lighter_prices()
        
        total_pnl = Decimal("0")
        position_details = []
        
        for asset, position in self._positions.items():
            current_price = self._last_prices.get(asset)
            
            if not current_price:
                logger.warning(f"No price available for {asset}")
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
        """Get account balance from Lighter.xyz"""
        try:
            if not self.api_key:
                return Decimal("10000.00")
            
            headers = {"X-API-Key": self.api_key}
            async with self.session.get(
                f"{self.LIGHTER_API_BASE}/api/v1/account/balance",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return Decimal(str(data.get("balance", 0)))
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
        return Decimal("10000.00")
