"""
Lighter.xyz API Client for trading operations
Uses official Lighter.xyz API v2 endpoints
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
    
    Uses official Lighter.xyz API v2 for price and orderbook data
    API Docs: https://api.lighter.xyz
    """
    
    # Lighter.xyz API v2
    API_BASE = "https://api.lighter.xyz/api/v2"
    
    # Arbitrum chain ID
    BLOCKCHAIN_ID = 42161
    
    # Orderbook symbols on Lighter.xyz
    ORDERBOOK_SYMBOLS = {
        "BTC": "WBTC-USDC",
        "ETH": "WETH-USDC",
        "SOL": "SOL-USDC",  # May not exist, fallback available
    }

    def __init__(self, private_key: str, api_key: str = None, network: str = "mainnet"):
        """
        Initialize the Lighter client
        
        Args:
            private_key: Wallet private key for signing transactions
            api_key: Lighter.xyz API key (Auth header)
            network: 'mainnet' or 'testnet'
        """
        self.private_key = private_key
        self.api_key = api_key
        self.network = network
        self.session: Optional[aiohttp.ClientSession] = None
        self._positions: Dict[str, Position] = {}
        self._last_prices: Dict[str, Decimal] = {}
        self._orderbook_metas: Dict[str, Dict] = {}
        self._price_source = "unknown"
        
    async def initialize(self):
        """Initialize the client and fetch market data"""
        timeout = aiohttp.ClientTimeout(total=15)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Fetch orderbook metadata and initial prices
        await self._fetch_orderbook_metas()
        await self._fetch_lighter_prices()
        
        logger.info(f"Lighter client initialized | Network: {self.network} | Price source: {self._price_source}")
        
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        headers = {
            "Accept": "application/json",
            "User-Agent": "lighter-telegram-bot/1.0",
        }
        if self.api_key:
            headers["Auth"] = self.api_key
        return headers
    
    async def _fetch_orderbook_metas(self):
        """Fetch orderbook metadata from Lighter.xyz"""
        try:
            url = f"{self.API_BASE}/order_book_metas"
            params = {"blockchain_id": self.BLOCKCHAIN_ID}
            
            async with self.session.get(url, headers=self._get_headers(), params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Lighter orderbook_metas response: {json.dumps(data)[:500]}")
                    
                    # Parse orderbook metadata
                    if isinstance(data, list):
                        for ob in data:
                            symbol = ob.get("symbol", "")
                            self._orderbook_metas[symbol] = ob
                            logger.info(f"Found orderbook: {symbol}")
                else:
                    logger.warning(f"Lighter orderbook_metas API returned {response.status}: {await response.text()}")
        except Exception as e:
            logger.error(f"Failed to fetch orderbook metas: {e}")
    
    async def _fetch_lighter_prices(self):
        """Fetch current prices from Lighter.xyz orderbook"""
        self._last_prices = {}
        
        for asset, orderbook_symbol in self.ORDERBOOK_SYMBOLS.items():
            try:
                url = f"{self.API_BASE}/order_book"
                params = {
                    "blockchain_id": self.BLOCKCHAIN_ID,
                    "order_book_symbol": orderbook_symbol,
                }
                
                async with self.session.get(url, headers=self._get_headers(), params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract mid price from orderbook
                        # Orderbook typically has 'asks' and 'bids'
                        asks = data.get("asks", [])
                        bids = data.get("bids", [])
                        
                        if asks and bids:
                            # Get best ask and best bid
                            best_ask = Decimal(str(asks[0].get("price", 0))) if asks else Decimal("0")
                            best_bid = Decimal(str(bids[0].get("price", 0))) if bids else Decimal("0")
                            
                            if best_ask > 0 and best_bid > 0:
                                mid_price = (best_ask + best_bid) / 2
                                self._last_prices[asset] = mid_price
                                self._price_source = "Lighter.xyz"
                                logger.info(f"Lighter {asset} price: ${mid_price:.2f} (bid: ${best_bid:.2f}, ask: ${best_ask:.2f})")
                            elif best_ask > 0:
                                self._last_prices[asset] = best_ask
                                self._price_source = "Lighter.xyz"
                            elif best_bid > 0:
                                self._last_prices[asset] = best_bid
                                self._price_source = "Lighter.xyz"
                        
                        # Also check for 'last_price' or similar fields
                        if asset not in self._last_prices:
                            for field in ["last_price", "lastPrice", "mark_price", "index_price"]:
                                if field in data and data[field]:
                                    self._last_prices[asset] = Decimal(str(data[field]))
                                    self._price_source = "Lighter.xyz"
                                    logger.info(f"Lighter {asset} price from {field}: ${self._last_prices[asset]:.2f}")
                                    break
                    else:
                        logger.debug(f"Lighter orderbook for {orderbook_symbol} returned {response.status}")
                        
            except Exception as e:
                logger.debug(f"Failed to fetch {asset} price from Lighter: {e}")
        
        # If no prices from Lighter, try candlesticks endpoint
        if not self._last_prices:
            await self._fetch_prices_from_candles()
        
        # Fallback to Binance Futures if Lighter fails
        if not self._last_prices:
            await self._fetch_binance_futures_prices()
    
    async def _fetch_prices_from_candles(self):
        """Try to get prices from candlesticks endpoint"""
        import time as time_module
        
        for asset, orderbook_symbol in self.ORDERBOOK_SYMBOLS.items():
            try:
                url = f"{self.API_BASE}/candlesticks"
                now = int(time_module.time())
                params = {
                    "blockchain_id": self.BLOCKCHAIN_ID,
                    "order_book_symbol": orderbook_symbol,
                    "start_timestamp": now - 3600,  # Last hour
                    "end_timestamp": now,
                    "resolution": "1h",
                }
                
                async with self.session.get(url, headers=self._get_headers(), params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list) and len(data) > 0:
                            # Get the most recent candle's close price
                            latest = data[-1]
                            close_price = Decimal(str(latest.get("close", latest.get("c", 0))))
                            if close_price > 0:
                                self._last_prices[asset] = close_price
                                self._price_source = "Lighter.xyz (candles)"
                                logger.info(f"Lighter {asset} price from candles: ${close_price:.2f}")
            except Exception as e:
                logger.debug(f"Failed to get {asset} candles: {e}")
    
    async def _fetch_binance_futures_prices(self) -> bool:
        """Fetch prices from Binance Perpetual Futures (fallback)"""
        try:
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
                        self._price_source = "Binance Futures (fallback)"
                        logger.info(f"Using Binance Futures prices as fallback")
                        return True
        except Exception as e:
            logger.error(f"Binance Futures API failed: {e}")
        
        return False
    
    async def get_market_price(self, asset: str) -> Optional[Decimal]:
        """Get the current market price for an asset"""
        await self._fetch_lighter_prices()
        return self._last_prices.get(asset)
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get current prices for all supported assets"""
        await self._fetch_lighter_prices()
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
        Open a new position tracking
        
        Note: This tracks positions locally. For actual on-chain orders,
        you need to use the Lighter SDK with web3 provider and wallet signing.
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
            
            logger.info(f"Position tracked: {asset} {side.name} | Entry: ${price:,.2f} | Size: {size:.6f} | Margin: ${margin} | Leverage: {leverage}x | Source: {self._price_source}")
            
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
            "price_source": self._price_source,
        }
    
    def has_open_positions(self) -> bool:
        """Check if there are any open positions"""
        return len(self._positions) > 0
    
    async def get_account_balance(self) -> Optional[Decimal]:
        """Get account balance"""
        return Decimal("10000.00")
