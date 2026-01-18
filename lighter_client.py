"""
Lighter.xyz API Client for trading operations
Integrates with Lighter.xyz DEX futures
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
    
    Uses Lighter.xyz API for price data with Binance perpetual futures as fallback
    """
    
    # Market IDs on Lighter.xyz
    MARKET_IDS = {
        "BTC": 0,
        "ETH": 1,
        "SOL": 2,
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
        self._positions: Dict[str, Position] = {}
        self._last_prices: Dict[str, Decimal] = {}
        self._price_source = "unknown"
        
    async def initialize(self):
        """Initialize the client and fetch market data"""
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Try to fetch prices
        await self._fetch_prices()
        
        logger.info(f"Lighter client initialized | Network: {self.network} | Price source: {self._price_source}")
        
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()
    
    async def _try_lighter_api(self) -> bool:
        """Try to fetch prices from Lighter.xyz API"""
        if not self.api_key:
            return False
        
        # Known Lighter.xyz API endpoints to try
        endpoints = [
            "https://api.lighter.xyz/api/v1/tickers",
            "https://api.lighter.xyz/api/v1/markets",
            "https://api.lighter.xyz/v1/tickers",
            "https://mainnet.lighter.xyz/api/v1/tickers",
        ]
        
        headers = {
            "X-API-Key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }
        
        for endpoint in endpoints:
            try:
                async with self.session.get(endpoint, headers=headers) as response:
                    logger.info(f"Lighter API {endpoint} -> Status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Lighter API response: {json.dumps(data)[:500]}")
                        
                        # Try to parse prices from response
                        if await self._parse_lighter_response(data):
                            self._price_source = "Lighter.xyz"
                            return True
            except Exception as e:
                logger.debug(f"Lighter endpoint {endpoint} failed: {e}")
        
        return False
    
    async def _parse_lighter_response(self, data: Any) -> bool:
        """Parse price data from Lighter API response"""
        try:
            if isinstance(data, dict):
                # Check for common response structures
                if "data" in data:
                    data = data["data"]
                if "markets" in data:
                    data = data["markets"]
                if "tickers" in data:
                    data = data["tickers"]
            
            if isinstance(data, list):
                for item in data:
                    self._extract_price_from_item(item)
            elif isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, dict):
                        value["symbol"] = key
                        self._extract_price_from_item(value)
            
            return len(self._last_prices) > 0
        except Exception as e:
            logger.error(f"Error parsing Lighter response: {e}")
            return False
    
    def _extract_price_from_item(self, item: dict):
        """Extract price from a single market item"""
        symbol = str(item.get("symbol", item.get("market", item.get("name", "")))).upper()
        
        # Try various price fields
        price = None
        for field in ["lastPrice", "last_price", "markPrice", "mark_price", 
                      "indexPrice", "index_price", "price", "last", "mid"]:
            if field in item:
                try:
                    price = Decimal(str(item[field]))
                    if price > 0:
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
    
    async def _fetch_binance_futures_prices(self) -> bool:
        """Fetch prices from Binance Perpetual Futures (as fallback)"""
        try:
            # Binance USDⓈ-M Futures API
            url = "https://fapi.binance.com/fapi/v1/ticker/price"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for item in data:
                        symbol = item.get("symbol", "")
                        price = Decimal(str(item.get("price", 0)))
                        
                        if symbol == "BTCUSDT":
                            self._last_prices["BTC"] = price
                        elif symbol == "ETHUSDT":
                            self._last_prices["ETH"] = price
                        elif symbol == "SOLUSDT":
                            self._last_prices["SOL"] = price
                    
                    if self._last_prices:
                        self._price_source = "Binance Futures"
                        return True
        except Exception as e:
            logger.error(f"Binance Futures API failed: {e}")
        
        return False
    
    async def _fetch_prices(self):
        """Fetch current prices - tries Lighter first, then Binance Futures"""
        # Clear old prices
        self._last_prices = {}
        
        # Try Lighter.xyz API first
        if await self._try_lighter_api():
            logger.info(f"Prices from Lighter.xyz: BTC=${self._last_prices.get('BTC')}, ETH=${self._last_prices.get('ETH')}, SOL=${self._last_prices.get('SOL')}")
            return
        
        # Fallback to Binance Perpetual Futures
        if await self._fetch_binance_futures_prices():
            logger.info(f"Prices from Binance Futures: BTC=${self._last_prices.get('BTC')}, ETH=${self._last_prices.get('ETH')}, SOL=${self._last_prices.get('SOL')}")
            return
        
        logger.error("Could not fetch prices from any source!")
    
    async def get_market_price(self, asset: str) -> Optional[Decimal]:
        """Get the current market price for an asset"""
        await self._fetch_prices()
        return self._last_prices.get(asset)
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get current prices for all supported assets"""
        await self._fetch_prices()
        return self._last_prices.copy()
    
    def get_price_source(self) -> str:
        """Get the current price source"""
        return self._price_source
    
    async def open_position(
        self,
        market_id: int,
        side: OrderSide,
        margin: float,
        leverage: int,
        asset: str
    ) -> Optional[Position]:
        """
        Open a new position
        
        Tracks positions locally using live futures prices.
        """
        try:
            # Get current market price
            price = await self.get_market_price(asset)
            if not price or price == 0:
                logger.error(f"Could not get price for {asset}")
                return None
            
            # Calculate position size
            notional_value = Decimal(str(margin)) * Decimal(str(leverage))
            size = notional_value / price
            
            # Calculate liquidation price
            margin_ratio = Decimal("1") / Decimal(str(leverage))
            if side == OrderSide.LONG:
                liquidation_price = price * (1 - margin_ratio * Decimal("0.9"))
            else:
                liquidation_price = price * (1 + margin_ratio * Decimal("0.9"))
            
            # Create position
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
            
            self._positions[asset] = position
            
            logger.info(f"Position opened: {asset} {side.name} | Entry: ${price:,.2f} | Size: {size:.6f} | Margin: ${margin} | Leverage: {leverage}x | Source: {self._price_source}")
            
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
            
            # Get current price
            current_price = await self.get_market_price(asset)
            if not current_price:
                logger.error(f"Could not get current price for {asset}")
                return None
            
            # Calculate PnL
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
        """Update PnL for all positions"""
        await self._fetch_prices()
        
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
            "price_source": self._price_source,
        }
    
    def has_open_positions(self) -> bool:
        """Check if there are any open positions"""
        return len(self._positions) > 0
    
    async def get_account_balance(self) -> Optional[Decimal]:
        """Get account balance"""
        return Decimal("10000.00")
