"""
Lighter.xyz Perpetual Futures API Client
Uses official lighter-sdk for REAL trading

Install: pip install lighter-sdk
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
    Client for Lighter.xyz Perpetual Futures - REAL TRADING
    
    Uses lighter-sdk (pip install lighter-sdk) for order execution
    """
    
    MAINNET_URL = "https://mainnet.zklighter.elliot.ai"
    TESTNET_URL = "https://testnet.zklighter.elliot.ai"
    
    MAINNET_WS = "wss://mainnet.zklighter.elliot.ai/stream"
    TESTNET_WS = "wss://testnet.zklighter.elliot.ai/stream"
    
    # Market indices on Lighter Perpetual Futures
    MARKET_INDICES = {
        "BTC": 1,
        "ETH": 0,
        "SOL": 2,
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
        self._order_counter = int(time.time())
        
        # Lighter SDK clients
        self._signer_client = None
        self._api_client = None
        self._sdk_available = False
        
    async def initialize(self):
        """Initialize the client"""
        timeout = aiohttp.ClientTimeout(total=15)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Initialize Lighter SDK for real trading
        await self._init_lighter_sdk()
        
        # Fetch initial prices
        await self._fetch_market_stats_rest()
        
        # Start WebSocket for real-time prices
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_listener())
        
        mode = "🟢 REAL TRADING" if self._sdk_available else "🟡 PAPER TRADING"
        logger.info(f"Lighter client initialized | {mode} | {self.network}")
        
    async def _init_lighter_sdk(self):
        """Initialize Lighter SDK for real order execution"""
        if not self.api_private_key or not self.api_key_index:
            logger.warning("Lighter API credentials not provided - PAPER TRADING mode")
            return
        
        if self.account_index is None or self.account_index < 0:
            logger.warning("Lighter account index not set - PAPER TRADING mode")
            logger.warning("Run: python find_account_index.py YOUR_WALLET_ADDRESS")
            return
        
        try:
            import lighter
            
            # Initialize Signer client for transactions
            self._signer_client = lighter.SignerClient(
                url=self.base_url,
                account_index=self.account_index,
                api_private_keys={self.api_key_index: self.api_private_key},
            )
            
            # Verify client is working
            err = self._signer_client.check_client()
            if err is not None:
                error_str = str(err).lower()
                
                if "invalid account index" in error_str or "account" in error_str:
                    logger.error(f"❌ Invalid account index: {self.account_index}")
                    logger.error("   Your account index is wrong!")
                    logger.error("   Run: python find_account_index.py YOUR_WALLET_ADDRESS")
                    logger.error("   Then update LIGHTER_ACCOUNT_INDEX in your .env file")
                elif "api" in error_str or "key" in error_str:
                    logger.error(f"❌ API key error: {err}")
                    logger.error("   Check your LIGHTER_API_PRIVATE_KEY and LIGHTER_API_KEY_INDEX")
                else:
                    logger.error(f"Lighter SDK error: {err}")
                
                # Clean up
                if self._signer_client:
                    try:
                        await self._signer_client.close()
                    except:
                        pass
                self._signer_client = None
                return
            
            self._sdk_available = True
            logger.info("🟢 Lighter SDK initialized - REAL TRADING enabled!")
            logger.info(f"   Account Index: {self.account_index}")
            logger.info(f"   API Key Index: {self.api_key_index}")
            
        except ImportError:
            logger.error("lighter-sdk not installed! Run: pip install lighter-sdk")
        except Exception as e:
            error_str = str(e).lower()
            
            if "invalid account index" in error_str:
                logger.error(f"❌ Invalid account index: {self.account_index}")
                logger.error("   Run: python find_account_index.py YOUR_WALLET_ADDRESS")
            else:
                logger.error(f"Failed to initialize Lighter SDK: {e}")
            
            # Clean up any partially initialized clients
            if self._signer_client:
                try:
                    await self._signer_client.close()
                except:
                    pass
                self._signer_client = None
    
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
            
        if self._signer_client:
            await self._signer_client.close()
            
        if self._api_client:
            await self._api_client.close()
            
        if self.session:
            await self.session.close()
    
    async def _fetch_market_stats_rest(self):
        """Fetch market stats via REST API"""
        try:
            url = f"{self.base_url}/api/v1/markets"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
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
                                                break
                                        except:
                                            pass
        except Exception as e:
            logger.debug(f"Failed to fetch markets: {e}")
        
        if not self._last_prices:
            await self._fetch_binance_futures_prices()
    
    async def _fetch_binance_futures_prices(self):
        """Fallback to Binance Futures"""
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
        except Exception as e:
            logger.error(f"Binance fallback failed: {e}")
    
    async def _ws_listener(self):
        """WebSocket listener for real-time perps prices"""
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws_connection = ws
                    logger.info(f"Connected to Lighter Perps WebSocket")
                    
                    # Subscribe to market stats
                    await ws.send(json.dumps({"type": "subscribe", "channel": "market_stats/all"}))
                    
                    for asset, market_id in self.MARKET_INDICES.items():
                        await ws.send(json.dumps({"type": "subscribe", "channel": f"market_stats/{market_id}"}))
                    
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            await self._handle_ws_message(data)
                        except json.JSONDecodeError:
                            pass
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket closed, reconnecting...")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(5)
    
    async def _handle_ws_message(self, data: dict):
        """Handle WebSocket messages"""
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
                        for price_field in ["mark_price", "index_price", "last_trade_price"]:
                            if price_field in market_stats and market_stats[price_field]:
                                try:
                                    price = Decimal(str(market_stats[price_field]))
                                    if price > 0:
                                        self._last_prices[asset] = price
                                        self._price_source = "Lighter.xyz Perps WS"
                                        break
                                except:
                                    pass
    
    async def get_market_price(self, asset: str) -> Optional[Decimal]:
        """Get current perpetual futures price"""
        if asset not in self._last_prices:
            await self._fetch_market_stats_rest()
        return self._last_prices.get(asset)
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get all prices"""
        return self._last_prices.copy()
    
    def get_price_source(self) -> str:
        return self._price_source
    
    def is_real_trading_enabled(self) -> bool:
        return self._sdk_available
    
    async def open_position(
        self,
        market_id: int,
        side: OrderSide,
        margin: float,
        leverage: int,
        asset: str
    ) -> Optional[Position]:
        """Open a perpetual futures position on Lighter.xyz"""
        try:
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
            
            self._order_counter += 1
            client_order_index = self._order_counter
            
            # Place REAL order if SDK available
            real_order_placed = False
            tx_hash = None
            
            if self._sdk_available and self._signer_client:
                real_order_placed, tx_hash = await self._place_real_order(
                    market_id=market_id,
                    side=side,
                    size=size,
                    price=price,
                    client_order_index=client_order_index,
                    asset=asset
                )
            
            order_id = tx_hash if tx_hash else f"{asset}_{side.name}_{int(time.time())}"
            
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
            
            mode = "🟢 REAL" if real_order_placed else "🟡 PAPER"
            logger.info(f"{mode} | {asset} {side.name} @ ${price:,.2f} | Size: {size:.6f} | Margin: ${margin}")
            
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
    ) -> tuple:
        """Place a REAL market order on Lighter.xyz"""
        try:
            if not self._signer_client:
                return False, None
            
            is_ask = side == OrderSide.SHORT
            
            # Convert to Lighter format
            # Base amount in smallest units (check market config for decimals)
            # For ETH: 1 ETH = 10000 base units (4 decimals)
            # For BTC: 1 BTC = 100000 base units (5 decimals)
            
            if asset == "BTC":
                base_amount = int(size * Decimal("100000"))
            elif asset == "ETH":
                base_amount = int(size * Decimal("10000"))
            else:
                base_amount = int(size * Decimal("10000"))
            
            # Price with 2 decimal places
            avg_execution_price = int(price * Decimal("100"))
            
            logger.info(f"Placing REAL order: {asset} {side.name}")
            logger.info(f"  base_amount: {base_amount}")
            logger.info(f"  avg_execution_price: {avg_execution_price}")
            logger.info(f"  is_ask: {is_ask}")
            
            # Call Lighter SDK
            tx, tx_hash, err = await self._signer_client.create_market_order(
                market_index=market_id,
                client_order_index=client_order_index,
                base_amount=base_amount,
                avg_execution_price=avg_execution_price,
                is_ask=is_ask,
            )
            
            if err is not None:
                logger.error(f"Order error: {err}")
                return False, None
            
            logger.info(f"✅ REAL order placed! TX: {tx_hash}")
            return True, tx_hash
                
        except Exception as e:
            logger.error(f"Error placing real order: {e}")
            return False, None
    
    async def close_position(self, asset: str) -> Optional[Dict[str, Any]]:
        """Close a position"""
        try:
            position = self._positions.get(asset)
            if not position:
                return None
            
            current_price = await self.get_market_price(asset)
            if not current_price:
                return None
            
            # Calculate PnL
            if position.side == "LONG":
                pnl = (current_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - current_price) * position.size
            
            # Close real position
            if self._sdk_available and self._signer_client:
                await self._close_real_position(position)
            
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
            logger.info(f"Position closed: {asset} | PnL: {pnl_str}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return None
    
    async def _close_real_position(self, position: Position) -> bool:
        """Close a real position by placing opposite order"""
        try:
            if not self._signer_client:
                return False
            
            close_side = OrderSide.SHORT if position.side == "LONG" else OrderSide.LONG
            current_price = await self.get_market_price(position.asset)
            if not current_price:
                return False
            
            is_ask = close_side == OrderSide.SHORT
            
            if position.asset == "BTC":
                base_amount = int(position.size * Decimal("100000"))
            elif position.asset == "ETH":
                base_amount = int(position.size * Decimal("10000"))
            else:
                base_amount = int(position.size * Decimal("10000"))
            
            avg_execution_price = int(current_price * Decimal("100"))
            
            self._order_counter += 1
            
            tx, tx_hash, err = await self._signer_client.create_market_order(
                market_index=position.market_id,
                client_order_index=self._order_counter,
                base_amount=base_amount,
                avg_execution_price=avg_execution_price,
                is_ask=is_ask,
            )
            
            if err is not None:
                logger.error(f"Close order error: {err}")
                return False
            
            logger.info(f"✅ Close order placed! TX: {tx_hash}")
            return True
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all positions"""
        results = []
        assets = list(self._positions.keys())
        for asset in assets:
            result = await self.close_position(asset)
            if result:
                results.append(result)
        return results
    
    async def get_position(self, asset: str) -> Optional[Position]:
        return self._positions.get(asset)
    
    async def get_all_positions(self) -> List[Position]:
        return list(self._positions.values())
    
    async def update_positions_pnl(self) -> Dict[str, Any]:
        """Update PnL for all positions"""
        total_pnl = Decimal("0")
        position_details = []
        
        for asset, position in self._positions.items():
            current_price = self._last_prices.get(asset)
            if not current_price:
                current_price = await self.get_market_price(asset)
                if not current_price:
                    continue
            
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
            "trading_mode": "🟢 REAL" if self._sdk_available else "🟡 PAPER",
        }
    
    def has_open_positions(self) -> bool:
        return len(self._positions) > 0
    
    async def get_account_balance(self) -> Optional[Decimal]:
        return Decimal("10000.00")
    
    def get_market_stats(self, market_id: int) -> Optional[Dict]:
        return self._market_stats.get(market_id)
