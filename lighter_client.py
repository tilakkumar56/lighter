"""
Lighter.xyz API Client for trading operations
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from decimal import Decimal
import aiohttp
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    LONG = "BUY"
    SHORT = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


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
    
    Lighter.xyz uses an orderbook model with on-chain settlement.
    """
    
    # API endpoints
    MAINNET_API = "https://api.lighter.xyz"
    TESTNET_API = "https://testnet-api.lighter.xyz"
    
    def __init__(self, private_key: str, api_key: str = None, network: str = "mainnet"):
        """
        Initialize the Lighter client
        
        Args:
            private_key: Wallet private key for signing transactions
            api_key: Optional API key for authenticated endpoints
            network: 'mainnet' or 'testnet'
        """
        self.private_key = private_key
        self.api_key = api_key
        self.network = network
        self.base_url = self.MAINNET_API if network == "mainnet" else self.TESTNET_API
        self.session: Optional[aiohttp.ClientSession] = None
        self._positions: Dict[int, Position] = {}
        
        # Market info cache
        self._markets: Dict[int, Dict] = {}
        
    async def initialize(self):
        """Initialize the client and fetch market data"""
        self.session = aiohttp.ClientSession()
        await self._fetch_markets()
        logger.info(f"Lighter client initialized on {self.network}")
        
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()
            
    async def _fetch_markets(self):
        """Fetch available markets from Lighter"""
        try:
            async with self.session.get(f"{self.base_url}/v1/markets") as response:
                if response.status == 200:
                    data = await response.json()
                    for market in data.get("markets", []):
                        self._markets[market["id"]] = market
                    logger.info(f"Fetched {len(self._markets)} markets")
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            # Use default market info if API fails
            self._markets = {
                0: {"id": 0, "symbol": "BTC-USD", "base_asset": "BTC"},
                1: {"id": 1, "symbol": "ETH-USD", "base_asset": "ETH"},
                2: {"id": 2, "symbol": "SOL-USD", "base_asset": "SOL"},
            }
    
    async def get_market_price(self, market_id: int) -> Optional[Decimal]:
        """Get the current market price for an asset"""
        try:
            async with self.session.get(f"{self.base_url}/v1/markets/{market_id}/ticker") as response:
                if response.status == 200:
                    data = await response.json()
                    return Decimal(str(data.get("last_price", 0)))
        except Exception as e:
            logger.error(f"Failed to get market price: {e}")
        return None
    
    async def get_prices(self) -> Dict[str, Decimal]:
        """Get current prices for all supported assets"""
        prices = {}
        for asset, market_id in [("BTC", 0), ("ETH", 1), ("SOL", 2)]:
            price = await self.get_market_price(market_id)
            if price:
                prices[asset] = price
        return prices
    
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
        
        Args:
            market_id: The market ID to trade
            side: OrderSide.LONG or OrderSide.SHORT
            margin: Margin amount in USD
            leverage: Leverage multiplier
            asset: Asset symbol (BTC, ETH, SOL)
            
        Returns:
            Position object if successful, None otherwise
        """
        try:
            # Get current market price
            price = await self.get_market_price(market_id)
            if not price:
                # Fallback to estimated prices if API fails
                fallback_prices = {"BTC": 45000, "ETH": 2500, "SOL": 100}
                price = Decimal(str(fallback_prices.get(asset, 100)))
            
            # Calculate position size based on margin and leverage
            notional_value = Decimal(str(margin)) * Decimal(str(leverage))
            size = notional_value / price
            
            # Calculate liquidation price (simplified)
            liquidation_buffer = Decimal("0.9") if side == OrderSide.LONG else Decimal("1.1")
            if side == OrderSide.LONG:
                liquidation_price = price * (1 - Decimal("1") / Decimal(str(leverage)) * liquidation_buffer)
            else:
                liquidation_price = price * (1 + Decimal("1") / Decimal(str(leverage)) * liquidation_buffer)
            
            # Create the order payload
            order_payload = {
                "market_id": market_id,
                "side": side.value,
                "type": OrderType.MARKET.value,
                "size": str(size),
                "margin": str(margin),
                "leverage": leverage,
            }
            
            logger.info(f"Opening {side.name} position: {order_payload}")
            
            # In production, this would sign and submit the transaction
            # For now, we simulate the position creation
            position = Position(
                market_id=market_id,
                asset=asset,
                side=side.name,
                size=size,
                entry_price=price,
                margin=Decimal(str(margin)),
                leverage=leverage,
                unrealized_pnl=Decimal("0"),
                liquidation_price=liquidation_price
            )
            
            self._positions[market_id] = position
            logger.info(f"Position opened: {asset} {side.name} @ {price}")
            
            return position
            
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return None
    
    async def close_position(self, market_id: int) -> Optional[Dict[str, Any]]:
        """
        Close an existing position
        
        Args:
            market_id: The market ID of the position to close
            
        Returns:
            Dict with close details including realized PnL
        """
        try:
            position = self._positions.get(market_id)
            if not position:
                logger.warning(f"No position found for market {market_id}")
                return None
            
            # Get current market price
            current_price = await self.get_market_price(market_id)
            if not current_price:
                # Use a simulated price change for demo
                import random
                change = Decimal(str(random.uniform(-0.02, 0.05)))
                current_price = position.entry_price * (1 + change)
            
            # Calculate PnL
            if position.side == "LONG":
                pnl = (current_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - current_price) * position.size
            
            result = {
                "market_id": market_id,
                "asset": position.asset,
                "side": position.side,
                "entry_price": float(position.entry_price),
                "exit_price": float(current_price),
                "size": float(position.size),
                "realized_pnl": float(pnl),
                "margin_returned": float(position.margin),
            }
            
            # Remove the position
            del self._positions[market_id]
            logger.info(f"Position closed: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return None
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all open positions"""
        results = []
        market_ids = list(self._positions.keys())
        
        for market_id in market_ids:
            result = await self.close_position(market_id)
            if result:
                results.append(result)
        
        return results
    
    async def get_position(self, market_id: int) -> Optional[Position]:
        """Get a specific position"""
        return self._positions.get(market_id)
    
    async def get_all_positions(self) -> List[Position]:
        """Get all open positions"""
        return list(self._positions.values())
    
    async def update_positions_pnl(self) -> Dict[str, Any]:
        """
        Update PnL for all positions and return summary
        
        Returns:
            Dict with position details and total PnL
        """
        total_pnl = Decimal("0")
        position_details = []
        
        for market_id, position in self._positions.items():
            current_price = await self.get_market_price(market_id)
            
            if not current_price:
                # Simulate small price movement for demo
                import random
                change = Decimal(str(random.uniform(-0.01, 0.02)))
                current_price = position.entry_price * (1 + change)
            
            # Calculate unrealized PnL
            if position.side == "LONG":
                pnl = (current_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - current_price) * position.size
            
            position.unrealized_pnl = pnl
            total_pnl += pnl
            
            pnl_percent = (pnl / position.margin) * 100
            
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
        """Get account balance"""
        try:
            # In production, this would query the actual balance
            # For demo, return a simulated balance
            return Decimal("10000.00")
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            return None
