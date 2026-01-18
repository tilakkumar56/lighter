"""
Lighter.xyz Futures Trading Telegram Bot

A bot for managing dual futures positions on Lighter.xyz with automated
profit booking and position reopening.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from decimal import Decimal

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    LIGHTER_API_PRIVATE_KEY,
    LIGHTER_API_KEY_INDEX,
    LIGHTER_ACCOUNT_INDEX,
    LIGHTER_NETWORK,
    SUPPORTED_ASSETS,
    ASSET_MARKET_IDS,
    MAX_LEVERAGE,
    MIN_LEVERAGE,
    MIN_MARGIN,
    MAX_MARGIN,
    PROFIT_CHECK_INTERVAL,
    REOPEN_DELAY,
    SELECTING_ASSET_1,
    SELECTING_DIRECTION_1,
    ENTERING_MARGIN_1,
    ENTERING_LEVERAGE_1,
    SELECTING_ASSET_2,
    SELECTING_DIRECTION_2,
    ENTERING_MARGIN_2,
    ENTERING_LEVERAGE_2,
    ENTERING_PROFIT_TARGET,
    CONFIRMING_SETUP,
)
from lighter_client import LighterClient, OrderSide, TradeSetup, DualTradeSetup

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global state
lighter_client: Optional[LighterClient] = None
user_setups: Dict[int, DualTradeSetup] = {}
monitoring_tasks: Dict[int, asyncio.Task] = {}
active_monitoring: Dict[int, bool] = {}


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    if not ALLOWED_USER_IDS:
        return True  # Allow all if no restrictions set
    return user_id in ALLOWED_USER_IDS


def get_asset_keyboard():
    """Create keyboard for asset selection"""
    keyboard = [
        [InlineKeyboardButton(asset, callback_data=f"asset_{asset}")]
        for asset in SUPPORTED_ASSETS
    ]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def get_direction_keyboard():
    """Create keyboard for direction selection"""
    keyboard = [
        [
            InlineKeyboardButton("📈 LONG", callback_data="direction_LONG"),
            InlineKeyboardButton("📉 SHORT", callback_data="direction_SHORT"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirm_keyboard():
    """Create keyboard for confirmation"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm & Start", callback_data="confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return
    
    welcome_message = """
🚀 *Welcome to Lighter.xyz Trading Bot!*

This bot helps you manage dual futures positions with automated profit booking.

*Available Commands:*
• /trade - Start a new dual trade setup
• /status - Check current PnL and positions
• /panic - Emergency close all positions
• /stop - Stop monitoring and close positions
• /help - Show this help message

*How it works:*
1. Select your first asset (BTC/ETH/SOL)
2. Choose direction (Long/Short)
3. Set margin and leverage
4. Repeat for second asset
5. Set profit target
6. Bot opens both trades and monitors
7. When profit target is reached, bot books profit and reopens after 50s

⚠️ *Risk Warning:* Trading futures involves significant risk. Only trade with funds you can afford to lose.
"""
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    await start(update, context)


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the trade setup conversation"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return ConversationHandler.END
    
    # Check if user already has active positions
    if user_id in monitoring_tasks and not monitoring_tasks[user_id].done():
        await update.message.reply_text(
            "⚠️ You already have an active trading session.\n"
            "Use /stop to stop the current session first."
        )
        return ConversationHandler.END
    
    # Initialize trade context
    context.user_data["trade_setup"] = {
        "trade1": {},
        "trade2": {},
    }
    
    await update.message.reply_text(
        "🔹 *Trade 1 Setup*\n\n"
        "Select the first asset to trade:",
        parse_mode="Markdown",
        reply_markup=get_asset_keyboard()
    )
    
    return SELECTING_ASSET_1


async def select_asset_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first asset selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    context.user_data["trade_setup"]["trade1"]["asset"] = asset
    context.user_data["trade_setup"]["trade1"]["market_id"] = ASSET_MARKET_IDS[asset]
    
    await query.edit_message_text(
        f"🔹 *Trade 1 Setup*\n\n"
        f"Asset: *{asset}*\n\n"
        f"Are you longing or shorting {asset}?",
        parse_mode="Markdown",
        reply_markup=get_direction_keyboard()
    )
    
    return SELECTING_DIRECTION_1


async def select_direction_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first trade direction selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    direction = query.data.replace("direction_", "")
    context.user_data["trade_setup"]["trade1"]["direction"] = direction
    
    asset = context.user_data["trade_setup"]["trade1"]["asset"]
    emoji = "📈" if direction == "LONG" else "📉"
    
    await query.edit_message_text(
        f"🔹 *Trade 1 Setup*\n\n"
        f"Asset: *{asset}*\n"
        f"Direction: *{emoji} {direction}*\n\n"
        f"Enter margin amount in $ (min: ${MIN_MARGIN}, max: ${MAX_MARGIN:,}):",
        parse_mode="Markdown"
    )
    
    return ENTERING_MARGIN_1


async def enter_margin_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first trade margin input"""
    try:
        margin = float(update.message.text.replace("$", "").replace(",", "").strip())
        
        if margin < MIN_MARGIN or margin > MAX_MARGIN:
            await update.message.reply_text(
                f"⚠️ Margin must be between ${MIN_MARGIN} and ${MAX_MARGIN:,}.\n"
                f"Please enter a valid amount:"
            )
            return ENTERING_MARGIN_1
        
        context.user_data["trade_setup"]["trade1"]["margin"] = margin
        
        trade1 = context.user_data["trade_setup"]["trade1"]
        emoji = "📈" if trade1["direction"] == "LONG" else "📉"
        
        await update.message.reply_text(
            f"🔹 *Trade 1 Setup*\n\n"
            f"Asset: *{trade1['asset']}*\n"
            f"Direction: *{emoji} {trade1['direction']}*\n"
            f"Margin: *${margin:,.2f}*\n\n"
            f"Enter leverage (min: {MIN_LEVERAGE}x, max: {MAX_LEVERAGE}x):",
            parse_mode="Markdown"
        )
        
        return ENTERING_LEVERAGE_1
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid amount. Please enter a numeric value:"
        )
        return ENTERING_MARGIN_1


async def enter_leverage_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first trade leverage input"""
    try:
        leverage = int(update.message.text.replace("x", "").replace("X", "").strip())
        
        if leverage < MIN_LEVERAGE or leverage > MAX_LEVERAGE:
            await update.message.reply_text(
                f"⚠️ Leverage must be between {MIN_LEVERAGE}x and {MAX_LEVERAGE}x.\n"
                f"Please enter a valid leverage:"
            )
            return ENTERING_LEVERAGE_1
        
        context.user_data["trade_setup"]["trade1"]["leverage"] = leverage
        
        trade1 = context.user_data["trade_setup"]["trade1"]
        emoji = "📈" if trade1["direction"] == "LONG" else "📉"
        
        await update.message.reply_text(
            f"✅ *Trade 1 Complete!*\n\n"
            f"Asset: *{trade1['asset']}*\n"
            f"Direction: *{emoji} {trade1['direction']}*\n"
            f"Margin: *${trade1['margin']:,.2f}*\n"
            f"Leverage: *{leverage}x*\n\n"
            f"─────────────────\n\n"
            f"🔸 *Trade 2 Setup*\n\n"
            f"Select the second asset to trade:",
            parse_mode="Markdown",
            reply_markup=get_asset_keyboard()
        )
        
        return SELECTING_ASSET_2
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid leverage. Please enter a numeric value:"
        )
        return ENTERING_LEVERAGE_1


async def select_asset_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second asset selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    context.user_data["trade_setup"]["trade2"]["asset"] = asset
    context.user_data["trade_setup"]["trade2"]["market_id"] = ASSET_MARKET_IDS[asset]
    
    await query.edit_message_text(
        f"🔸 *Trade 2 Setup*\n\n"
        f"Asset: *{asset}*\n\n"
        f"Are you longing or shorting {asset}?",
        parse_mode="Markdown",
        reply_markup=get_direction_keyboard()
    )
    
    return SELECTING_DIRECTION_2


async def select_direction_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second trade direction selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    direction = query.data.replace("direction_", "")
    context.user_data["trade_setup"]["trade2"]["direction"] = direction
    
    asset = context.user_data["trade_setup"]["trade2"]["asset"]
    emoji = "📈" if direction == "LONG" else "📉"
    
    await query.edit_message_text(
        f"🔸 *Trade 2 Setup*\n\n"
        f"Asset: *{asset}*\n"
        f"Direction: *{emoji} {direction}*\n\n"
        f"Enter margin amount in $ (min: ${MIN_MARGIN}, max: ${MAX_MARGIN:,}):",
        parse_mode="Markdown"
    )
    
    return ENTERING_MARGIN_2


async def enter_margin_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second trade margin input"""
    try:
        margin = float(update.message.text.replace("$", "").replace(",", "").strip())
        
        if margin < MIN_MARGIN or margin > MAX_MARGIN:
            await update.message.reply_text(
                f"⚠️ Margin must be between ${MIN_MARGIN} and ${MAX_MARGIN:,}.\n"
                f"Please enter a valid amount:"
            )
            return ENTERING_MARGIN_2
        
        context.user_data["trade_setup"]["trade2"]["margin"] = margin
        
        trade2 = context.user_data["trade_setup"]["trade2"]
        emoji = "📈" if trade2["direction"] == "LONG" else "📉"
        
        await update.message.reply_text(
            f"🔸 *Trade 2 Setup*\n\n"
            f"Asset: *{trade2['asset']}*\n"
            f"Direction: *{emoji} {trade2['direction']}*\n"
            f"Margin: *${margin:,.2f}*\n\n"
            f"Enter leverage (min: {MIN_LEVERAGE}x, max: {MAX_LEVERAGE}x):",
            parse_mode="Markdown"
        )
        
        return ENTERING_LEVERAGE_2
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid amount. Please enter a numeric value:"
        )
        return ENTERING_MARGIN_2


async def enter_leverage_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second trade leverage input"""
    try:
        leverage = int(update.message.text.replace("x", "").replace("X", "").strip())
        
        if leverage < MIN_LEVERAGE or leverage > MAX_LEVERAGE:
            await update.message.reply_text(
                f"⚠️ Leverage must be between {MIN_LEVERAGE}x and {MAX_LEVERAGE}x.\n"
                f"Please enter a valid leverage:"
            )
            return ENTERING_LEVERAGE_2
        
        context.user_data["trade_setup"]["trade2"]["leverage"] = leverage
        
        trade1 = context.user_data["trade_setup"]["trade1"]
        trade2 = context.user_data["trade_setup"]["trade2"]
        
        emoji1 = "📈" if trade1["direction"] == "LONG" else "📉"
        emoji2 = "📈" if trade2["direction"] == "LONG" else "📉"
        
        total_margin = trade1["margin"] + trade2["margin"]
        
        await update.message.reply_text(
            f"✅ *Trade 2 Complete!*\n\n"
            f"Asset: *{trade2['asset']}*\n"
            f"Direction: *{emoji2} {trade2['direction']}*\n"
            f"Margin: *${trade2['margin']:,.2f}*\n"
            f"Leverage: *{leverage}x*\n\n"
            f"─────────────────\n\n"
            f"💰 *Total Margin: ${total_margin:,.2f}*\n\n"
            f"Enter your profit target in $ (e.g., 50 for $50 profit):",
            parse_mode="Markdown"
        )
        
        return ENTERING_PROFIT_TARGET
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid leverage. Please enter a numeric value:"
        )
        return ENTERING_LEVERAGE_2


async def enter_profit_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle profit target input"""
    try:
        profit_target = float(update.message.text.replace("$", "").replace(",", "").strip())
        
        if profit_target <= 0:
            await update.message.reply_text(
                "⚠️ Profit target must be greater than 0.\n"
                "Please enter a valid amount:"
            )
            return ENTERING_PROFIT_TARGET
        
        context.user_data["trade_setup"]["profit_target"] = profit_target
        
        trade1 = context.user_data["trade_setup"]["trade1"]
        trade2 = context.user_data["trade_setup"]["trade2"]
        
        emoji1 = "📈" if trade1["direction"] == "LONG" else "📉"
        emoji2 = "📈" if trade2["direction"] == "LONG" else "📉"
        
        total_margin = trade1["margin"] + trade2["margin"]
        
        summary = f"""
📋 *TRADE SETUP SUMMARY*

*Trade 1:*
  Asset: {trade1['asset']}
  Direction: {emoji1} {trade1['direction']}
  Margin: ${trade1['margin']:,.2f}
  Leverage: {trade1['leverage']}x
  Position Size: ${trade1['margin'] * trade1['leverage']:,.2f}

*Trade 2:*
  Asset: {trade2['asset']}
  Direction: {emoji2} {trade2['direction']}
  Margin: ${trade2['margin']:,.2f}
  Leverage: {trade2['leverage']}x
  Position Size: ${trade2['margin'] * trade2['leverage']:,.2f}

─────────────────
💰 *Total Margin: ${total_margin:,.2f}*
🎯 *Profit Target: ${profit_target:,.2f}*
─────────────────

Confirm to open both positions?
"""
        
        await update.message.reply_text(
            summary,
            parse_mode="Markdown",
            reply_markup=get_confirm_keyboard()
        )
        
        return CONFIRMING_SETUP
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid amount. Please enter a numeric value:"
        )
        return ENTERING_PROFIT_TARGET


async def confirm_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle trade setup confirmation"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Create trade setup objects
    trade1_data = context.user_data["trade_setup"]["trade1"]
    trade2_data = context.user_data["trade_setup"]["trade2"]
    profit_target = context.user_data["trade_setup"]["profit_target"]
    
    trade1 = TradeSetup(
        asset=trade1_data["asset"],
        direction=trade1_data["direction"],
        margin=trade1_data["margin"],
        leverage=trade1_data["leverage"],
        market_id=trade1_data["market_id"],
    )
    
    trade2 = TradeSetup(
        asset=trade2_data["asset"],
        direction=trade2_data["direction"],
        margin=trade2_data["margin"],
        leverage=trade2_data["leverage"],
        market_id=trade2_data["market_id"],
    )
    
    dual_setup = DualTradeSetup(
        trade1=trade1,
        trade2=trade2,
        profit_target=profit_target,
    )
    
    user_setups[user_id] = dual_setup
    
    await query.edit_message_text(
        "⏳ Fetching market prices and opening positions...",
        parse_mode="Markdown"
    )
    
    # Open both positions
    try:
        side1 = OrderSide.LONG if trade1.direction == "LONG" else OrderSide.SHORT
        side2 = OrderSide.LONG if trade2.direction == "LONG" else OrderSide.SHORT
        
        pos1 = await lighter_client.open_position(
            market_id=trade1.market_id,
            side=side1,
            margin=trade1.margin,
            leverage=trade1.leverage,
            asset=trade1.asset,
        )
        
        pos2 = await lighter_client.open_position(
            market_id=trade2.market_id,
            side=side2,
            margin=trade2.margin,
            leverage=trade2.leverage,
            asset=trade2.asset,
        )
        
        if pos1 and pos2:
            emoji1 = "📈" if trade1.direction == "LONG" else "📉"
            emoji2 = "📈" if trade2.direction == "LONG" else "📉"
            
            total_margin = trade1.margin + trade2.margin
            price_source = lighter_client.get_price_source()
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"""
✅ *POSITIONS OPENED SUCCESSFULLY!*

*Position 1:*
  {emoji1} {trade1.asset} {trade1.direction}
  Entry: ${float(pos1.entry_price):,.2f}
  Size: {float(pos1.size):.6f} {trade1.asset}
  Margin: ${trade1.margin:,.2f} @ {trade1.leverage}x
  Liq. Price: ${float(pos1.liquidation_price):,.2f}

*Position 2:*
  {emoji2} {trade2.asset} {trade2.direction}
  Entry: ${float(pos2.entry_price):,.2f}
  Size: {float(pos2.size):.6f} {trade2.asset}
  Margin: ${trade2.margin:,.2f} @ {trade2.leverage}x
  Liq. Price: ${float(pos2.liquidation_price):,.2f}

─────────────────
💰 *Total Margin: ${total_margin:,.2f}*
🎯 *Profit Target: ${profit_target:,.2f}*
📊 *Price Source: {price_source}*
─────────────────

🔄 *Monitoring started!*
Checking prices every {PROFIT_CHECK_INTERVAL} seconds...

Use /status to check PnL
Use /stop to stop monitoring
""",
                parse_mode="Markdown"
            )
            
            # Start monitoring task
            active_monitoring[user_id] = True
            monitoring_tasks[user_id] = asyncio.create_task(
                monitor_positions(user_id, chat_id, context.bot)
            )
            
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Failed to open one or both positions. Could not fetch market prices. Please try again.",
            )
            
    except Exception as e:
        logger.error(f"Error opening positions: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error opening positions: {str(e)}",
        )
    
    return ConversationHandler.END


async def monitor_positions(user_id: int, chat_id: int, bot) -> None:
    """Monitor positions for profit target"""
    global active_monitoring
    
    last_status_update = 0
    status_update_interval = 60  # Send status update every 60 seconds
    
    try:
        while active_monitoring.get(user_id, False):
            if not lighter_client.has_open_positions():
                logger.info(f"No open positions for user {user_id}")
                break
            
            # Update PnL
            pnl_data = await lighter_client.update_positions_pnl()
            total_pnl = pnl_data["total_unrealized_pnl"]
            
            # Check if we have the user setup
            if user_id not in user_setups:
                break
            
            setup = user_setups[user_id]
            
            # Log current PnL status
            current_time = time.time()
            if current_time - last_status_update >= status_update_interval:
                pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
                progress = (total_pnl / setup.profit_target) * 100 if setup.profit_target > 0 else 0
                logger.info(f"User {user_id} | PnL: ${total_pnl:+,.2f} | Target: ${setup.profit_target:,.2f} | Progress: {progress:.1f}%")
                last_status_update = current_time
            
            # Check if profit target reached
            if total_pnl >= setup.profit_target:
                logger.info(f"🎯 Profit target reached! PnL: ${total_pnl:,.2f}, Target: ${setup.profit_target:,.2f}")
                
                # Close all positions
                results = await lighter_client.close_all_positions()
                
                if not results:
                    logger.error("Failed to close positions")
                    await asyncio.sleep(PROFIT_CHECK_INTERVAL)
                    continue
                
                total_realized_pnl = sum(r["realized_pnl"] for r in results)
                
                # Send notification
                positions_text = ""
                for r in results:
                    pnl_sign = "+" if r["realized_pnl"] >= 0 else ""
                    positions_text += f"\n  • {r['asset']} {r['side']}: {pnl_sign}${r['realized_pnl']:.2f}"
                
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"""
🎉🎉🎉 *CONGRATS! PROFIT BOOKED!* 🎉🎉🎉

💰 *Total Profit: ${total_realized_pnl:+,.2f}*

*Closed Positions:*{positions_text}

⏳ Reopening positions in {REOPEN_DELAY} seconds...
""",
                    parse_mode="Markdown"
                )
                
                # Wait before reopening
                await asyncio.sleep(REOPEN_DELAY)
                
                # Check if still active
                if not active_monitoring.get(user_id, False):
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⏹️ Monitoring was stopped. Positions will not be reopened.",
                        parse_mode="Markdown"
                    )
                    break
                
                # Reopen positions with same setup
                await reopen_positions(user_id, chat_id, bot, setup)
            
            # Wait before next check
            await asyncio.sleep(PROFIT_CHECK_INTERVAL)
            
    except asyncio.CancelledError:
        logger.info(f"Monitoring cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Error in monitoring: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Monitoring error: {str(e)}",
        )
    finally:
        active_monitoring[user_id] = False


async def reopen_positions(user_id: int, chat_id: int, bot, setup: DualTradeSetup) -> None:
    """Reopen positions with the same setup"""
    try:
        side1 = OrderSide.LONG if setup.trade1.direction == "LONG" else OrderSide.SHORT
        side2 = OrderSide.LONG if setup.trade2.direction == "LONG" else OrderSide.SHORT
        
        pos1 = await lighter_client.open_position(
            market_id=setup.trade1.market_id,
            side=side1,
            margin=setup.trade1.margin,
            leverage=setup.trade1.leverage,
            asset=setup.trade1.asset,
        )
        
        pos2 = await lighter_client.open_position(
            market_id=setup.trade2.market_id,
            side=side2,
            margin=setup.trade2.margin,
            leverage=setup.trade2.leverage,
            asset=setup.trade2.asset,
        )
        
        if pos1 and pos2:
            emoji1 = "📈" if setup.trade1.direction == "LONG" else "📉"
            emoji2 = "📈" if setup.trade2.direction == "LONG" else "📉"
            
            await bot.send_message(
                chat_id=chat_id,
                text=f"""
🔄 *POSITIONS REOPENED!*

*Position 1:*
  {emoji1} {setup.trade1.asset} {setup.trade1.direction}
  Entry: ${float(pos1.entry_price):,.2f}
  Size: {float(pos1.size):.6f} {setup.trade1.asset}
  Margin: ${setup.trade1.margin:,.2f} @ {setup.trade1.leverage}x

*Position 2:*
  {emoji2} {setup.trade2.asset} {setup.trade2.direction}
  Entry: ${float(pos2.entry_price):,.2f}
  Size: {float(pos2.size):.6f} {setup.trade2.asset}
  Margin: ${setup.trade2.margin:,.2f} @ {setup.trade2.leverage}x

🎯 *Target: ${setup.profit_target:,.2f}*

🔄 Monitoring for profit target...
""",
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Failed to reopen positions. Could not fetch market prices. Monitoring stopped.",
            )
            active_monitoring[user_id] = False
            
    except Exception as e:
        logger.error(f"Error reopening positions: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error reopening positions: {str(e)}",
        )
        active_monitoring[user_id] = False


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - Check current PnL"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return
    
    if not lighter_client.has_open_positions():
        await update.message.reply_text(
            "📊 *No Open Positions*\n\n"
            "Use /trade to start a new trading session.",
            parse_mode="Markdown"
        )
        return
    
    # Get current PnL
    pnl_data = await lighter_client.update_positions_pnl()
    
    positions_text = ""
    for pos in pnl_data["positions"]:
        emoji = "📈" if pos["side"] == "LONG" else "📉"
        pnl_emoji = "🟢" if pos["unrealized_pnl"] >= 0 else "🔴"
        
        positions_text += f"""
*{pos['asset']} {emoji} {pos['side']}*
  Entry: ${pos['entry_price']:,.2f}
  Current: ${pos['current_price']:,.2f}
  Margin: ${pos['margin']:,.2f}
  Leverage: {pos['leverage']}x
  {pnl_emoji} PnL: ${pos['unrealized_pnl']:+,.2f} ({pos['pnl_percent']:+.2f}%)
"""
    
    total_pnl = pnl_data["total_unrealized_pnl"]
    total_emoji = "🟢" if total_pnl >= 0 else "🔴"
    
    # Get profit target if available
    target_text = ""
    if user_id in user_setups:
        setup = user_setups[user_id]
        progress = (total_pnl / setup.profit_target) * 100 if setup.profit_target > 0 else 0
        target_text = f"\n🎯 Target: ${setup.profit_target:,.2f} ({progress:.1f}% reached)"
    
    monitoring_status = "🔄 Monitoring Active" if active_monitoring.get(user_id, False) else "⏸️ Monitoring Paused"
    price_source = pnl_data.get("price_source", "unknown")
    
    await update.message.reply_text(
        f"""
📊 *POSITION STATUS*

{positions_text}
─────────────────
{total_emoji} *Total PnL: ${total_pnl:+,.2f}*{target_text}

📊 Price Source: {price_source}
{monitoring_status}
""",
        parse_mode="Markdown"
    )


async def panic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /panic command - Emergency close all positions"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return
    
    if not lighter_client.has_open_positions():
        await update.message.reply_text(
            "📊 *No Open Positions*\n\n"
            "Nothing to close.",
            parse_mode="Markdown"
        )
        return
    
    await update.message.reply_text("🚨 *PANIC SELL INITIATED...*", parse_mode="Markdown")
    
    # Stop monitoring
    active_monitoring[user_id] = False
    if user_id in monitoring_tasks:
        monitoring_tasks[user_id].cancel()
    
    # Close all positions
    results = await lighter_client.close_all_positions()
    
    if results:
        total_pnl = sum(r["realized_pnl"] for r in results)
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        
        positions_text = ""
        for r in results:
            pos_emoji = "🟢" if r["realized_pnl"] >= 0 else "🔴"
            positions_text += f"\n  • {r['asset']}: ${r['realized_pnl']:+,.2f}"
        
        await update.message.reply_text(
            f"""
🚨 *ALL POSITIONS CLOSED!*

*Closed Positions:*{positions_text}

─────────────────
{pnl_emoji} *Total PnL: ${total_pnl:+,.2f}*

Monitoring stopped.
Use /trade to start a new session.
""",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ Failed to close positions. Please try again or check manually.",
        )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command - Stop monitoring and close positions"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return
    
    # Stop monitoring
    was_monitoring = active_monitoring.get(user_id, False)
    active_monitoring[user_id] = False
    
    if user_id in monitoring_tasks:
        monitoring_tasks[user_id].cancel()
    
    # Close all positions if any
    if lighter_client.has_open_positions():
        results = await lighter_client.close_all_positions()
        
        if results:
            total_pnl = sum(r["realized_pnl"] for r in results)
            pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
            
            positions_text = ""
            for r in results:
                positions_text += f"\n  • {r['asset']}: ${r['realized_pnl']:+,.2f}"
            
            await update.message.reply_text(
                f"""
⏹️ *TRADING STOPPED*

*Closed Positions:*{positions_text}

─────────────────
{pnl_emoji} *Final PnL: ${total_pnl:+,.2f}*

Use /trade to start a new session.
""",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⏹️ *TRADING STOPPED*\n\n"
                "No positions were closed.",
                parse_mode="Markdown"
            )
    else:
        if was_monitoring:
            await update.message.reply_text(
                "⏹️ *MONITORING STOPPED*\n\n"
                "No open positions.\n"
                "Use /trade to start a new session.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "ℹ️ No active trading session.\n\n"
                "Use /trade to start a new session.",
                parse_mode="Markdown"
            )
    
    # Clear user setup
    if user_id in user_setups:
        del user_setups[user_id]


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation"""
    await update.message.reply_text(
        "❌ Trade setup cancelled.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def setup_commands(application: Application) -> None:
    """Setup bot commands for the menu"""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("trade", "Start a new dual trade setup"),
        BotCommand("status", "Check current PnL and positions"),
        BotCommand("panic", "Emergency close all positions"),
        BotCommand("stop", "Stop monitoring and close positions"),
        BotCommand("help", "Show help message"),
    ]
    await application.bot.set_my_commands(commands)


async def post_init(application: Application) -> None:
    """Initialize after application startup"""
    global lighter_client
    
    # Initialize Lighter client with perps API config
    lighter_client = LighterClient(
        api_private_key=LIGHTER_API_PRIVATE_KEY,
        api_key_index=LIGHTER_API_KEY_INDEX,
        account_index=LIGHTER_ACCOUNT_INDEX,
        network=LIGHTER_NETWORK,
    )
    await lighter_client.initialize()
    
    # Setup bot commands
    await setup_commands(application)
    
    logger.info("Bot initialized successfully!")


def main():
    """Main function to run the bot"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        print("Error: Please set TELEGRAM_BOT_TOKEN in your .env file")
        return
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Create conversation handler for trade setup
    trade_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("trade", trade)],
        states={
            SELECTING_ASSET_1: [CallbackQueryHandler(select_asset_1)],
            SELECTING_DIRECTION_1: [CallbackQueryHandler(select_direction_1)],
            ENTERING_MARGIN_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_margin_1)],
            ENTERING_LEVERAGE_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_leverage_1)],
            SELECTING_ASSET_2: [CallbackQueryHandler(select_asset_2)],
            SELECTING_DIRECTION_2: [CallbackQueryHandler(select_direction_2)],
            ENTERING_MARGIN_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_margin_2)],
            ENTERING_LEVERAGE_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_leverage_2)],
            ENTERING_PROFIT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_profit_target)],
            CONFIRMING_SETUP: [CallbackQueryHandler(confirm_setup)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel$"),
        ],
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(trade_conv_handler)
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("panic", panic))
    application.add_handler(CommandHandler("stop", stop))
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
