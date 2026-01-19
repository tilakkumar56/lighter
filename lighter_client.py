"""
Lighter.xyz Perpetual Futures API Client
Uses official Lighter SDK and WebSocket for real-time data

API Docs: https://apidocs.lighter.xyz/docs/get-started-for-programmers-1
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
import websockets

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
    Client for Lighter.xyz Perpetual Futures
    
    Uses:
    - REST API for transactions
    - WebSocket for real-time market data
    
    API Base: https://mainnet.zklighter.elliot.ai
    WebSocket: wss://mainnet.zklighter.elliot.ai/stream
    """
    
    # Lighter.xyz API endpoints
    MAINNET_URL = "https://mainnet.zklighter.elliot.ai"
    TESTNET_URL = "https://testnet.zklighter.elliot.ai"
    
    MAINNET_WS = "wss://mainnet.zklighter.elliot.ai/stream"
    TESTNET_WS = "wss://testnet.zklighter.elliot.ai/stream"
    
    # Market indices on Lighter (perpetual futures)
    # Market 0 = ETH-USD, Market 1 = BTC-USD based on docs examples
    MARKET_INDICES = {
        "BTC": 1,  # BTC-USD perpetual
        "ETH": 0,  # ETH-USD perpetual
        "SOL": 2,  # SOL-USD perpetual (if available)
    }
    
    MARKET_SYMBOLS = {
        0: "ETH",
        1: "BTC",
        2: "SOL",
    }

    def __init__(
        self, 
        api_private_key: str = None,
        api_key_index: int = None,
        account_index: int = None,
        network: str = "mainnet"
    ):
        """
        Initialize the Lighter client
        
        Args:
            api_private_key: API private key generated from Lighter
            api_key_index: API key index (3-254)
            account_index: Your Lighter account index
            network: 'mainnet' or 'testnet'
        """
        self.api_private_key = api_private_key
        self.api_key_index = api_key_index
        self.account_index = account_index
        self.network = network
        
        self.base_url = self.MAINNET_URL if network == "mainnet" else self.TESTNET_URL
        self.ws_url = self.MAINNET_WS if network == "mainnet" else self.TESTNET_WS
        
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection = None
        self._positions: Dict[str, Position] = {}
        self._last_prices: Dict[str, Decimal] = {}
        self._market_stats: Dict[int, Dict] = {}
        self._price_source = "unknown"
        self._ws_task = None
        self._running = False
        
    async def initialize(self):
        """Initialize the client and connect to WebSocket"""
        timeout = aiohttp.ClientTimeout(total=15)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Fetch initial prices via REST API
        await self._fetch_market_stats_rest()
        
        # Start WebSocket connection for real-time updates
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_listener())
        
        logger.info(f"Lighter client initialized | Network: {self.network} | URL: {self.base_url}")
        
    async def close(self):
        """Close all connections"""
        self._running = False
        
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        
        if self.ws_connection:
            await self.ws_connection.close()
            
        if self.session:
            await self.session.close()
    
    async def _fetch_market_stats_rest(self):
        """Fetch market stats via REST API"""
        try:
            # Try to get market info
            url = f"{self.base_url}/api/v1/markets"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Markets data: {json.dumps(data)[:500]}")
                    
                    # Parse markets data for prices
                    if isinstance(data, list):
                        for market in data:
                            market_id = market.get("market_index", market.get("market_id"))
                            asset = self.MARKET_SYMBOLS.get(market_id)
                            if asset:
                                for price_field in ["mark_price", "index_price", "last_price"]:
                                    if price_field in market and market[price_field]:
                                        try:
                                            price = Decimal(str(market[price_field]))
                                            if price > 0:
                                                self._last_prices[asset] = price
                                                self._price_source = "Lighter.xyz REST (markets)"
                                                logger.info(f"Got {asset} price from markets: ${price:,.2f}")
                                                break
                                        except:
                                            pass
        except Exception as e:
            logger.debug(f"Failed to fetch markets: {e}")
        
        # Fetch orderbook for each market to get prices
        for asset, market_id in self.MARKET_INDICES.items():
            if asset in self._last_prices:
                continue  # Already have price
                
            try:
                url = f"{self.base_url}/api/v1/orderbook"
                params = {"market_index": market_id}
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"Orderbook for {asset}: {json.dumps(data)[:300]}")
                        
                        # Extract mid price from orderbook
                        asks = data.get("asks", [])
                        bids = data.get("bids", [])
                        
                        if asks and bids:
                            best_ask = Decimal(str(asks[0].get("price", asks[0]) if isinstance(asks[0], dict) else asks[0]))
                            best_bid = Decimal(str(bids[0].get("price", bids[0]) if isinstance(bids[0], dict) else bids[0]))
                            if best_ask > 0 and best_bid > 0:
                                self._last_prices[asset] = (best_ask + best_bid) / 2
                                self._price_source = "Lighter.xyz REST (orderbook)"
                                logger.info(f"Got {asset} price from orderbook: ${self._last_prices[asset]:,.2f}")
            except Exception as e:
                logger.debug(f"Failed to fetch orderbook for {asset}: {e}")
        
        # If still no prices, try Binance as last resort
        if not self._last_prices:
            await self._fetch_binance_futures_prices()
    
    async def _fetch_binance_futures_prices(self):
        """Fallback to Binance Futures for prices"""
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/price"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for item in data:
                        symbol = item.get("symbol", "")
                        price = Decimal(str(item.get("price", 0)))
                        if symbol == "BTCUSDT" and "BTC" not in self._last_prices:
                            self._last_prices["BTC"] = price
                        elif symbol == "ETHUSDT" and "ETH" not in self._last_prices:
                            self._last_prices["ETH"] = price
                        elif symbol == "SOLUSDT" and "SOL" not in self._last_prices:
                            self._last_prices["SOL"] = price
                    
                    if self._last_prices:
                        self._price_source = "Binance Futures (fallback)"
                        logger.info(f"Using Binance Futures prices as fallback")
        except Exception as e:
            logger.error(f"Binance fallback failed: {e}")
    
    async def _ws_listener(self):
        """WebSocket listener for real-time market data"""
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws_connection = ws
                    logger.info(f"Connected to Lighter WebSocket: {self.ws_url}")
                    
                    # Subscribe to market stats for all markets
                    subscribe_msg = {
                        "type": "subscribe",
                        "channel": "market_stats/all"
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("Sent subscription: market_stats/all")
                    
                    # Also subscribe to individual markets
                    for asset, market_id in self.MARKET_INDICES.items():
                        sub_msg = {
                            "type": "subscribe",
                            "channel": f"market_stats/{market_id}"
                        }
                        await ws.send(json.dumps(sub_msg))
                        logger.info(f"Sent subscription: market_stats/{market_id} ({asset})")
                    
                    # Listen for messages
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            # Log first few messages to debug
                            if len(self._last_prices) == 0:
                                logger.info(f"WS raw message: {message[:500]}")
                            await self._handle_ws_message(data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON from WebSocket: {message[:100]}")
                            
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}, reconnecting...")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(5)
    
    async def _handle_ws_message(self, data: dict):
        """Handle incoming WebSocket messages"""
        msg_type = data.get("type", "")
        channel = data.get("channel", "")
        
        # Log all incoming messages for debugging
        logger.debug(f"WS message type: {msg_type}, channel: {channel}")
        
        if "market_stats" in msg_type or "market_stats" in channel:
            # Handle market stats update
            market_stats = data.get("market_stats", {})
            
            # Log received data
            logger.info(f"Received market_stats: {json.dumps(market_stats)[:300]}")
            
            if isinstance(market_stats, dict):
                market_id = market_stats.get("market_id")
                if market_id is not None:
                    self._market_stats[market_id] = market_stats
                    
                    # Extract prices
                    asset = self.MARKET_SYMBOLS.get(market_id)
                    if asset:
                        # Prefer mark_price, then index_price, then last_trade_price
                        for price_field in ["mark_price", "index_price", "last_trade_price"]:
                            if price_field in market_stats and market_stats[price_field]:
                                try:
                                    price = Decimal(str(market_stats[price_field]))
                                    if price > 0:
                                        self._last_prices[asset] = price
                                        self._price_source = f"Lighter.xyz WS ({price_field})"
                                        logger.info(f"Updated {asset} price: ${price:,.2f} from {price_field}")
                                        break
                                except Exception as e:
                                    logger.warning(f"Failed to parse price: {e}")
        else:
            # Log unknown message types
            logger.debug(f"Unknown WS message: {json.dumps(data)[:200]}")
    
    async def get_market_price(self, asset: str) -> Optional[Decimal]:
        """Get the current market price for an asset"""
        # If we don't have price from WS, try REST
        if asset not in self._last_prices or self._last_prices.get(asset, 0) == 0:
            logger.info(f"No WS price for {asset}, fetching via REST...")
            await self._fetch_market_stats_rest()
        
        price = self._last_prices.get(asset)
        if price:
            logger.info(f"Price for {asset}: ${price:,.2f} (source: {self._price_source})")
        return price
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get current prices for all supported assets"""
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
        Open a new position on Lighter.xyz
        
        Note: For actual order execution, this would use the SignerClient
        to sign and submit transactions. Current implementation tracks
        positions locally for price monitoring.
        """
        try:
            # Get current market price
            price = await self.get_market_price(asset)
            if not price or price == 0:
                logger.error(f"Could not get Lighter price for {asset}")
                return None
            
            # Calculate position size
            notional_value = Decimal(str(margin)) * Decimal(str(leverage))
            size = notional_value / price
            
            # Calculate liquidation price (simplified)
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
        """Update PnL for all positions using Lighter prices"""
        total_pnl = Decimal("0")
        position_details = []
        
        for asset, position in self._positions.items():
            current_price = self._last_prices.get(asset)
            
            if not current_price:
                # Try to fetch if not available
                current_price = await self.get_market_price(asset)
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
        """Get account balance from Lighter"""
        # Would need auth token to get actual balance
        return Decimal("10000.00")
    
    def get_market_stats(self, market_id: int) -> Optional[Dict]:
        """Get cached market stats for a market"""
        return self._market_stats.get(market_id)
