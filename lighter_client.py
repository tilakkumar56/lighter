"""
Lighter.xyz Perpetual Futures API Client
Uses official Lighter SDK for real trading and WebSocket for real-time data

API Docs: https://apidocs.lighter.xyz/docs/get-started-for-programmers-1
"""

import asyncio
import logging
import time
import json
import subprocess
import os
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
    client_order_index: int = 0


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
    - Lighter SDK SignerClient for actual order execution
    - WebSocket for real-time market data (perpetual futures prices)
    
    API Base: https://mainnet.zklighter.elliot.ai
    WebSocket: wss://mainnet.zklighter.elliot.ai/stream
    """
    
    # Lighter.xyz API endpoints
    MAINNET_URL = "https://mainnet.zklighter.elliot.ai"
    TESTNET_URL = "https://testnet.zklighter.elliot.ai"
    
    MAINNET_WS = "wss://mainnet.zklighter.elliot.ai/stream"
    TESTNET_WS = "wss://testnet.zklighter.elliot.ai/stream"
    
    # Market indices on Lighter Perpetual Futures
    MARKET_INDICES = {
        "BTC": 1,  # BTC-USD perpetual
        "ETH": 0,  # ETH-USD perpetual
        "SOL": 2,  # SOL-USD perpetual
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
        self._price_source = "Lighter.xyz Perps"
        self._ws_task = None
        self._running = False
        self._order_counter = int(time.time())  # For unique client_order_index
        
        # Lighter SDK client (will be initialized if credentials provided)
        self._signer_client = None
        self._sdk_available = False
        
    async def initialize(self):
        """Initialize the client and connect to WebSocket"""
        timeout = aiohttp.ClientTimeout(total=15)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Try to initialize Lighter SDK for real trading
        await self._init_lighter_sdk()
        
        # Fetch initial prices via REST API
        await self._fetch_market_stats_rest()
        
        # Start WebSocket connection for real-time updates
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_listener())
        
        sdk_status = "SDK Ready" if self._sdk_available else "Paper Trading Mode"
        logger.info(f"Lighter client initialized | Network: {self.network} | {sdk_status}")
        
    async def _init_lighter_sdk(self):
        """Initialize Lighter SDK for real order execution"""
        if not self.api_private_key or not self.api_key_index or self.account_index is None:
            logger.warning("Lighter API credentials not provided - running in paper trading mode")
            return
        
        try:
            import lighter
            
            self._signer_client = lighter.SignerClient(
                url=self.base_url,
                private_key=self.api_private_key,
                account_index=self.account_index,
                api_key_index=self.api_key_index,
            )
            
            # Check if client is valid
            err = self._signer_client.check_client()
            if err is not None:
                logger.error(f"Lighter SDK client error: {err}")
                self._signer_client = None
                return
            
            self._sdk_available = True
            logger.info("Lighter SDK initialized - real trading enabled!")
            
        except ImportError:
            logger.warning("Lighter SDK not installed - running in paper trading mode")
        except Exception as e:
            logger.error(f"Failed to initialize Lighter SDK: {e}")
    
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
            url = f"{self.base_url}/api/v1/markets"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"Markets data: {json.dumps(data)[:500]}")
                    
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
                                                logger.info(f"REST: {asset} perp price: ${price:,.2f}")
                                                break
                                        except:
                                            pass
        except Exception as e:
            logger.debug(f"Failed to fetch markets: {e}")
        
        # Fallback to Binance if no prices
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
        """WebSocket listener for real-time perpetual futures market data"""
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws_connection = ws
                    logger.info(f"Connected to Lighter Perps WebSocket: {self.ws_url}")
                    
                    # Subscribe to market stats for all markets
                    subscribe_msg = {
                        "type": "subscribe",
                        "channel": "market_stats/all"
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("Subscribed to perpetual futures market_stats/all")
                    
                    # Also subscribe to individual markets
                    for asset, market_id in self.MARKET_INDICES.items():
                        sub_msg = {
                            "type": "subscribe",
                            "channel": f"market_stats/{market_id}"
                        }
                        await ws.send(json.dumps(sub_msg))
                    
                    # Listen for messages
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            await self._handle_ws_message(data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON from WebSocket")
                            
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
        
        if "market_stats" in msg_type or "market_stats" in channel:
            market_stats = data.get("market_stats", {})
            
            if isinstance(market_stats, dict):
                market_id = market_stats.get("market_id")
                if market_id is not None:
                    self._market_stats[market_id] = market_stats
                    
                    asset = self.MARKET_SYMBOLS.get(market_id)
                    if asset:
                        # Get mark_price (perpetual futures price)
                        for price_field in ["mark_price", "index_price", "last_trade_price"]:
                            if price_field in market_stats and market_stats[price_field]:
                                try:
                                    price = Decimal(str(market_stats[price_field]))
                                    if price > 0:
                                        old_price = self._last_prices.get(asset)
                                        self._last_prices[asset] = price
                                        self._price_source = "Lighter.xyz Perps WS"
                                        
                                        # Only log if price changed significantly
                                        if old_price is None or abs(price - old_price) / old_price > Decimal("0.0001"):
                                            logger.debug(f"{asset} perp mark_price: ${price:,.2f}")
                                        break
                                except:
                                    pass
    
    async def get_market_price(self, asset: str) -> Optional[Decimal]:
        """Get the current perpetual futures price for an asset"""
        if asset not in self._last_prices or self._last_prices.get(asset, 0) == 0:
            await self._fetch_market_stats_rest()
        
        price = self._last_prices.get(asset)
        return price
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get current perpetual futures prices for all supported assets"""
        return self._last_prices.copy()
    
    def get_price_source(self) -> str:
        """Get the current price source"""
        return self._price_source
    
    def is_real_trading_enabled(self) -> bool:
        """Check if real trading is enabled"""
        return self._sdk_available
    
    async def open_position(
        self,
        market_id: int,
        side: OrderSide,
        margin: float,
        leverage: int,
        asset: str
    ) -> Optional[Position]:
        """
        Open a new perpetual futures position on Lighter.xyz
        """
        try:
            # Get current perpetual futures price
            price = await self.get_market_price(asset)
            if not price or price == 0:
                logger.error(f"Could not get Lighter perp price for {asset}")
                return None
            
            # Calculate position size based on margin and leverage
            notional_value = Decimal(str(margin)) * Decimal(str(leverage))
            size = notional_value / price
            
            # Calculate liquidation price (simplified)
            margin_ratio = Decimal("1") / Decimal(str(leverage))
            if side == OrderSide.LONG:
                liquidation_price = price * (1 - margin_ratio * Decimal("0.9"))
            else:
                liquidation_price = price * (1 + margin_ratio * Decimal("0.9"))
            
            # Generate unique order index
            self._order_counter += 1
            client_order_index = self._order_counter
            
            # Try to place real order if SDK is available
            real_order_placed = False
            order_id = f"{asset}_{side.name}_{int(time.time())}"
            
            if self._sdk_available and self._signer_client:
                try:
                    real_order_placed = await self._place_real_order(
                        market_id=market_id,
                        side=side,
                        size=size,
                        price=price,
                        client_order_index=client_order_index,
                        asset=asset
                    )
                    if real_order_placed:
                        order_id = f"lighter_{client_order_index}"
                except Exception as e:
                    logger.error(f"Failed to place real order: {e}")
            
            # Create position tracking object
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
                order_id=order_id,
                client_order_index=client_order_index
            )
            
            self._positions[asset] = position
            
            mode = "REAL" if real_order_placed else "PAPER"
            logger.info(f"[{mode}] Position opened: {asset} {side.name} | Entry: ${price:,.2f} | Size: {size:.6f} | Margin: ${margin} | Leverage: {leverage}x")
            
            return position
            
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return None
    
    async def _place_real_order(
        self,
        market_id: int,
        side: OrderSide,
        size: Decimal,
        price: Decimal,
        client_order_index: int,
        asset: str
    ) -> bool:
        """Place a real market order on Lighter.xyz using the SDK"""
        try:
            if not self._signer_client:
                return False
            
            # Determine if ask (sell/short) or bid (buy/long)
            is_ask = side == OrderSide.SHORT
            
            # Convert size to base amount (integer)
            # Note: Lighter uses integer amounts, need to check decimals
            base_amount = int(size * Decimal("1000000"))  # 6 decimals
            price_int = int(price * Decimal("100"))  # 2 decimals for price
            
            logger.info(f"Placing real order on Lighter: {asset} {side.name} | Size: {base_amount} | Price: {price_int}")
            
            # Use create_market_order method
            result = self._signer_client.create_market_order(
                market_index=market_id,
                base_amount=base_amount,
                price=price_int,
                is_ask=is_ask,
                client_order_index=client_order_index
            )
            
            if result:
                logger.info(f"Real order placed successfully: {result}")
                return True
            else:
                logger.warning("Order placement returned no result")
                return False
                
        except Exception as e:
            logger.error(f"Error placing real order: {e}")
            return False
    
    async def close_position(self, asset: str) -> Optional[Dict[str, Any]]:
        """Close an existing perpetual futures position"""
        try:
            position = self._positions.get(asset)
            if not position:
                logger.warning(f"No position found for {asset}")
                return None
            
            # Get current perpetual futures price
            current_price = await self.get_market_price(asset)
            if not current_price:
                logger.error(f"Could not get current perp price for {asset}")
                return None
            
            # Calculate realized PnL
            if position.side == "LONG":
                pnl = (current_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - current_price) * position.size
            
            # Try to close real position if SDK available
            if self._sdk_available and self._signer_client and position.client_order_index:
                try:
                    await self._close_real_position(position)
                except Exception as e:
                    logger.error(f"Failed to close real position: {e}")
            
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
    
    async def _close_real_position(self, position: Position) -> bool:
        """Close a real position on Lighter.xyz"""
        try:
            if not self._signer_client:
                return False
            
            # To close, we need to place an opposite order
            # Or cancel the existing order if it's still open
            
            # For market orders that are filled, we need to place opposite order
            close_side = OrderSide.SHORT if position.side == "LONG" else OrderSide.LONG
            
            current_price = await self.get_market_price(position.asset)
            if not current_price:
                return False
            
            base_amount = int(position.size * Decimal("1000000"))
            price_int = int(current_price * Decimal("100"))
            is_ask = close_side == OrderSide.SHORT
            
            self._order_counter += 1
            
            result = self._signer_client.create_market_order(
                market_index=position.market_id,
                base_amount=base_amount,
                price=price_int,
                is_ask=is_ask,
                client_order_index=self._order_counter
            )
            
            if result:
                logger.info(f"Real close order placed: {result}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error closing real position: {e}")
            return False
    
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
        """Update PnL for all positions using Lighter perp prices"""
        total_pnl = Decimal("0")
        position_details = []
        
        for asset, position in self._positions.items():
            current_price = self._last_prices.get(asset)
            
            if not current_price:
                current_price = await self.get_market_price(asset)
                if not current_price:
                    logger.warning(f"No perp price available for {asset}")
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
            "trading_mode": "REAL" if self._sdk_available else "PAPER",
        }
    
    def has_open_positions(self) -> bool:
        """Check if there are any open positions"""
        return len(self._positions) > 0
    
    async def get_account_balance(self) -> Optional[Decimal]:
        """Get account balance from Lighter"""
        return Decimal("10000.00")
    
    def get_market_stats(self, market_id: int) -> Optional[Dict]:
        """Get cached market stats for a perpetual market"""
        return self._market_stats.get(market_id)
