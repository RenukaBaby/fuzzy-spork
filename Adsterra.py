#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║           ADSTERRA AUTOMATION BOT - GOD LEVEL EDITION           ║
║              User Credentials via Telegram + Logout             ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import random
import logging
import sys
import os
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ================================================================
#                        LOGGING SETUP
# ================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AdsterraBot")

# ================================================================
#                     HARD-CODED CONFIG
# ================================================================
TELEGRAM_BOT_TOKEN: str = "8766573450:AAGDkv16RZOKPb8jqEZTGVoO5SsjmYnK6zI"
TELEGRAM_CHAT_ID:   str = "3797306274"

ADSTERRA_LOGIN_URL:     str = "https://publishers.adsterra.com/login"
ADSTERRA_SMARTLINK_URL: str = "https://publishers.adsterra.com/smartlink"

# ================================================================
#                   CONVERSATION STATES
# ================================================================
(
    STATE_EMAIL,
    STATE_PASSWORD,
    STATE_LOGOUT_CONFIRM,
) = range(3)

# ================================================================
#                      SESSION STORE
# ================================================================
class SessionStore:
    """
    Holds all runtime state for ONE user session.
    Designed to be fully resettable via logout.
    """

    def __init__(self) -> None:
        self.email:     Optional[str]            = None
        self.password:  Optional[str]            = None
        self.page:      Optional[Page]           = None
        self.browser:   Optional[Browser]        = None
        self.ctx:       Optional[BrowserContext] = None
        self.logged_in: bool                     = False
        self._playwright                         = None
        self._lock = asyncio.Lock()

    # ── Convenience ──────────────────────────────────────────
    @property
    def has_credentials(self) -> bool:
        return bool(self.email and self.password)

    @property
    def browser_alive(self) -> bool:
        return self.browser is not None

    # ── Full Reset ───────────────────────────────────────────
    async def full_logout(self) -> None:
        """Wipe credentials AND kill browser."""
        async with self._lock:
            self.email     = None
            self.password  = None
            self.logged_in = False
            await self._destroy_browser()

    # ── Browser Teardown ─────────────────────────────────────
    async def _destroy_browser(self) -> None:
        for obj, label in [
            (self.page,    "page"),
            (self.ctx,     "context"),
            (self.browser, "browser"),
        ]:
            if obj:
                try:
                    await obj.close()
                    logger.info("✅ Closed %s", label)
                except Exception as exc:
                    logger.warning("⚠️  Error closing %s: %s", label, exc)

        if self._playwright:
            try:
                await self._playwright.stop()
                logger.info("✅ Playwright stopped")
            except Exception as exc:
                logger.warning("⚠️  Playwright stop error: %s", exc)

        self.page        = None
        self.ctx         = None
        self.browser     = None
        self._playwright = None


# Single global session
SESSION = SessionStore()

# ================================================================
#                  ANTI-DETECTION HELPERS
# ================================================================
USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
]

STEALTH_SCRIPT: str = """
    Object.defineProperty(navigator, 'webdriver',  { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',    { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages',  { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
    window.chrome = { runtime: {} };
"""


async def human_delay(min_s: float = 1.2, max_s: float = 4.0) -> None:
    delay = random.uniform(min_s, max_s)
    logger.debug("💤 Delay %.2fs", delay)
    await asyncio.sleep(delay)


async def human_type(page: Page, selector: str, text: str) -> None:
    await page.click(selector)
    await human_delay(0.3, 0.7)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(40, 110))
    await human_delay(0.3, 0.8)


# ================================================================
#                  KEYBOARD FACTORY
# ================================================================
def main_menu(logged_in: bool = False) -> InlineKeyboardMarkup:
    """Dynamically build main menu based on login state."""
    if logged_in:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Create Smartlink",  callback_data="create_smartlink")],
            [InlineKeyboardButton("📊 Session Status",    callback_data="status")],
            [InlineKeyboardButton("🚪 Logout",            callback_data="logout")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login to Adsterra",    callback_data="login")],
        [InlineKeyboardButton("📊 Session Status",       callback_data="status")],
    ])


CONFIRM_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Yes, Logout", callback_data="logout_confirm"),
        InlineKeyboardButton("❌ Cancel",      callback_data="logout_cancel"),
    ]
])

# ================================================================
#                  TELEGRAM UTILITY
# ================================================================
async def safe_edit(query, text: str, keyboard=None) -> None:
    """Edit a callback message safely."""
    kwargs = {"text": text, "parse_mode": "HTML"}
    if keyboard:
        kwargs["reply_markup"] = keyboard
    try:
        await query.edit_message_text(**kwargs)
    except Exception as exc:
        logger.warning("safe_edit failed: %s", exc)


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Push a notification to the hard-coded admin chat."""
    try:
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)


# ================================================================
#                  PLAYWRIGHT ENGINE
# ================================================================
async def get_page() -> Page:
    """Return existing page or spin up a fresh browser."""
    if SESSION.page and not SESSION.page.is_closed():
        logger.info("♻️  Reusing existing browser page")
        return SESSION.page

    logger.info("🌐 Launching new Playwright browser…")
    SESSION._playwright = await async_playwright().start()

    SESSION.browser = await SESSION._playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1366,768",
            "--disable-gpu",
        ],
    )

    SESSION.ctx = await SESSION.browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/New_York",
    )

    await SESSION.ctx.add_init_script(STEALTH_SCRIPT)
    SESSION.page = await SESSION.ctx.new_page()
    SESSION.page.set_default_timeout(45_000)
    logger.info("✅ Browser ready")
    return SESSION.page


# ================================================================
#                  CORE AUTOMATION — LOGIN
# ================================================================
async def automation_login() -> dict:
    """
    Automate Adsterra login.
    Returns {"success": bool, "message": str}
    """
    try:
        page = await get_page()

        logger.info("🔑 Navigating to login page…")
        await page.goto(ADSTERRA_LOGIN_URL, wait_until="networkidle")
        await human_delay(2.0, 4.0)

        # ── Fill email ────────────────────────────────────────
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="email" i]',
        ]
        email_filled = False
        for sel in email_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.email)
                    email_filled = True
                    logger.info("📧 Email filled via: %s", sel)
                    break
            except Exception:
                continue

        if not email_filled:
            return {"success": False, "message": "Email input field not found on login page."}

        await human_delay(0.8, 1.5)

        # ── Fill password ─────────────────────────────────────
        pass_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="password" i]',
        ]
        pass_filled = False
        for sel in pass_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.password)
                    pass_filled = True
                    logger.info("🔑 Password filled via: %s", sel)
                    break
            except Exception:
                continue

        if not pass_filled:
            return {"success": False, "message": "Password input field not found on login page."}

        await human_delay(1.0, 2.0)

        # ── Submit ────────────────────────────────────────────
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
        ]
        submitted = False
        for sel in submit_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    submitted = True
                    logger.info("🖱️  Submitted via: %s", sel)
                    break
            except Exception:
                continue

        if not submitted:
            return {"success": False, "message": "Submit button not found."}

        await page.wait_for_load_state("networkidle")
        await human_delay(4.0, 7.0)

        current_url = page.url.lower()
        logger.info("📍 Post-login URL: %s", current_url)

        # ── Validate success ──────────────────────────────────
        success_signals = [
            "dashboard" in current_url,
            "publisher" in current_url,
            "smartlink" in current_url,
            "/home"     in current_url,
            await page.locator("text=Dashboard").count() > 0,
            await page.locator("text=Smartlink").count() > 0,
            await page.locator("text=Log out").count() > 0,
            await page.locator("text=Logout").count() > 0,
        ]

        if any(success_signals):
            SESSION.logged_in = True
            logger.info("✅ Login successful!")
            return {"success": True, "message": "Login successful"}

        # ── Grab page error if present ────────────────────────
        error_selectors = [
            ".alert-danger",
            ".error-message",
            "[class*='error']",
            "[class*='alert']",
            "p.text-red",
        ]
        for sel in error_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    err = (await el.first.inner_text()).strip()
                    if err:
                        return {"success": False, "message": f"Site error: {err}"}
            except Exception:
                continue

        return {
            "success": False,
            "message": (
                "Login failed — credentials may be wrong, "
                "or 2FA / CAPTCHA is blocking access."
            ),
        }

    except Exception as exc:
        logger.exception("Login automation exception")
        return {"success": False, "message": f"Unexpected error: {exc}"}


# ================================================================
#                CORE AUTOMATION — CREATE SMARTLINK
# ================================================================
async def automation_create_smartlink() -> dict:
    """
    Automate Smartlink creation.
    Returns {"success": bool, "message": str, "url": str|None, "name": str|None}
    """
    try:
        page = await get_page()

        logger.info("🔗 Navigating to Smartlinks page…")
        await page.goto(ADSTERRA_SMARTLINK_URL, wait_until="networkidle")
        await human_delay(3.0, 5.5)

        # ── Find & click Create button ────────────────────────
        create_selectors = [
            "text=Create Smartlink",
            "text=New Smartlink",
            "text=Add Smartlink",
            "button:has-text('Create')",
            "a:has-text('Create')",
            "[data-action='create']",
            ".btn-create",
        ]
        clicked = False
        for sel in create_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    clicked = True
                    logger.info("🖱️  Create clicked via: %s", sel)
                    break
            except Exception:
                continue

        if not clicked:
            return {
                "success": False,
                "message": "Could not find 'Create Smartlink' button. Dashboard layout may have changed.",
                "url": None,
                "name": None,
            }

        await human_delay(2.5, 4.5)

        # ── Fill name ─────────────────────────────────────────
        smartlink_name = f"AutoLink_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        name_selectors = [
            'input[name="name"]',
            'input[placeholder*="name" i]',
            'input[placeholder*="title" i]',
            'input[type="text"]:first-of-type',
        ]
        for sel in name_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, smartlink_name)
                    logger.info("📛 Name filled: %s", smartlink_name)
                    break
            except Exception:
                continue

        await human_delay(1.0, 2.0)

        # ── Select category ───────────────────────────────────
        cat_selectors = [
            'select[name="category"]',
            'select[name="vertical"]',
            'select[name="type"]',
        ]
        for sel in cat_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.select_option(sel, index=1)
                    logger.info("📂 Category selected via: %s", sel)
                    await human_delay(1.0, 2.0)
                    break
            except Exception:
                continue

        # ── Submit ────────────────────────────────────────────
        submit_selectors = [
            "text=Create",
            "text=Save",
            "text=Submit",
            'button[type="submit"]',
            ".btn-primary",
        ]
        for sel in submit_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    logger.info("🖱️  Form submitted via: %s", sel)
                    break
            except Exception:
                continue

        await human_delay(5.0, 9.0)

        # ── Extract URL ───────────────────────────────────────
        url_selectors = [
            "input[value^='https://']",
            "input[value^='http://']",
            "[class*='smartlink'] input",
            "[class*='link'] input",
            "[class*='url'] input",
        ]
        for sel in url_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    extracted = await el.input_value()
                    if extracted.startswith("http"):
                        logger.info("✅ URL extracted: %s", extracted)
                        return {
                            "success": True,
                            "message": "Smartlink created successfully!",
                            "url": extracted,
                            "name": smartlink_name,
                        }
            except Exception:
                continue

        return {
            "success": True,
            "message": "Smartlink likely created but URL could not be auto-extracted. Check your dashboard.",
            "url": None,
            "name": smartlink_name,
        }

    except Exception as exc:
        logger.exception("Smartlink creation exception")
        return {"success": False, "message": f"Unexpected error: {exc}", "url": None, "name": None}


# ================================================================
#                  TELEGRAM — /start
# ================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "🟢 Active" if SESSION.logged_in else "🔴 Not logged in"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"

    text = (
        f"👋 <b>Hello, {user.first_name}!</b>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🤖 <b>Adsterra Automation Bot</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"📌 Session  : {status_icon}\n"
        f"👤 Account  : {account}\n"
        f"🕐 Time     : {now}\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"Choose an option below 👇"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )


# ================================================================
#                  TELEGRAM — /status
# ================================================================
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_icon = "🟢 Active"   if SESSION.logged_in   else "🔴 Inactive"
    browser_st  = "🟢 Running"  if SESSION.browser_alive else "⚫ Closed"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"

    text = (
        f"<b>📊 Live Session Report</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔐 Login   : {status_icon}\n"
        f"👤 Account : {account}\n"
        f"🌐 Browser : {browser_st}\n"
        f"🕐 Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )


# ================================================================
#                  TELEGRAM — /cancel
# ================================================================
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ <b>Operation cancelled.</b>",
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#               CONVERSATION — LOGIN FLOW
# ================================================================
async def conv_ask_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: ask user for email."""
    query = update.callback_query
    await query.answer()

    if SESSION.logged_in:
        await safe_edit(
            query,
            (
                f"✅ <b>Already logged in!</b>\n\n"
                f"👤 Account: <code>{SESSION.email}</code>\n\n"
                f"Use 🚪 <b>Logout</b> first to switch accounts."
            ),
            keyboard=main_menu(SESSION.logged_in),
        )
        return ConversationHandler.END

    await safe_edit(
        query,
        (
            "🔐 <b>Adsterra Login</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "📧 <b>Step 1 of 2</b>\n\n"
            "Please send your <b>Adsterra email address</b>:\n\n"
            "<i>Type /cancel to abort.</i>"
        ),
    )
    return STATE_EMAIL


async def conv_receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive email, ask for password."""
    email = update.message.text.strip()

    # Basic validation
    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "⚠️ <b>That doesn't look like a valid email.</b>\n"
            "Please send a valid email address:",
            parse_mode="HTML",
        )
        return STATE_EMAIL

    SESSION.email = email
    logger.info("📧 Email received: %s", email)

    # Delete user's email message for privacy
    try:
        await update.message.delete()
    except Exception:
        pass

    await update.message.reply_text(
        (
            "✅ <b>Email received!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🔑 <b>Step 2 of 2</b>\n\n"
            "Now send your <b>Adsterra password</b>:\n\n"
            "<i>Your message will be deleted immediately for security.\n"
            "Type /cancel to abort.</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_PASSWORD


async def conv_receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive password, trigger login."""
    SESSION.password = update.message.text.strip()
    logger.info("🔑 Password received, starting automation…")

    # Immediately delete password message
    try:
        await update.message.delete()
    except Exception:
        pass

    progress_msg = await update.message.reply_text(
        (
            "⏳ <b>Logging in…</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🌐 Launching secure browser…\n"
            "🔑 Filling credentials…\n"
            "⏳ Waiting for response…\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            "<i>This may take 15–30 seconds.</i>"
        ),
        parse_mode="HTML",
    )

    result = await automation_login()

    if result["success"]:
        text = (
            f"✅ <b>Login Successful!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 Account : <code>{SESSION.email}</code>\n"
            f"🕐 Time    : {datetime.now().strftime('%H:%M:%S')}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"You can now create Smartlinks! 🎉"
        )
        await notify_admin(
            context,
            f"🟢 <b>Login Event</b>\n"
            f"👤 <code>{SESSION.email}</code>\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        )
    else:
        # Wipe credentials on failure
        SESSION.email    = None
        SESSION.password = None
        text = (
            f"❌ <b>Login Failed</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"⚠️ {result['message']}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"Please try again with correct credentials."
        )

    try:
        await progress_msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu(SESSION.logged_in),
        )
    except Exception:
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu(SESSION.logged_in),
        )

    return ConversationHandler.END


# ================================================================
#               CONVERSATION — LOGOUT FLOW
# ================================================================
async def conv_ask_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask user to confirm logout."""
    query = update.callback_query
    await query.answer()

    if not SESSION.email and not SESSION.logged_in:
        await safe_edit(
            query,
            "⚠️ <b>No active session to logout from.</b>",
            keyboard=main_menu(False),
        )
        return ConversationHandler.END

    account = f"<code>{SESSION.email}</code>" if SESSION.email else "Unknown"
    await safe_edit(
        query,
        (
            f"🚪 <b>Confirm Logout</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 Account : {account}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"This will:\n"
            f"  • Clear your credentials\n"
            f"  • Close all browser sessions\n"
            f"  • End your Adsterra session\n\n"
            f"<b>Are you sure?</b>"
        ),
        keyboard=CONFIRM_KEYBOARD,
    )
    return STATE_LOGOUT_CONFIRM


async def conv_logout_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute logout after confirmation."""
    query = update.callback_query
    await query.answer()

    old_email = SESSION.email or "Unknown"

    await safe_edit(
        query,
        "⏳ <b>Logging out…</b>\nClosing browser sessions…",
    )

    await SESSION.full_logout()
    logger.info("✅ Logout completed for %s", old_email)

    text = (
        f"✅ <b>Logged Out Successfully!</b>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"👤 Account : <code>{old_email}</code>\n"
        f"🕐 Time    : {datetime.now().strftime('%H:%M:%S')}\n"
        f"🌐 Browser : Closed\n"
        f"🔐 Session : Cleared\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"Use 🔐 Login to start a new session."
    )

    await safe_edit(query, text, keyboard=main_menu(False))
    await notify_admin(
        context,
        f"🔴 <b>Logout Event</b>\n"
        f"👤 <code>{old_email}</code>\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    )
    return ConversationHandler.END


async def conv_logout_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User cancelled logout."""
    query = update.callback_query
    await query.answer()
    await safe_edit(
        query,
        "✅ <b>Logout cancelled.</b> Your session is still active.",
        keyboard=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#               INLINE BUTTON — SMARTLINK & STATUS
# ================================================================
async def inline_create_smartlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not SESSION.logged_in:
        await safe_edit(
            query,
            (
                "🔴 <b>Not Logged In!</b>\n\n"
                "Please login first before creating Smartlinks."
            ),
            keyboard=main_menu(False),
        )
        return ConversationHandler.END

    await safe_edit(
        query,
        (
            "⏳ <b>Creating Smartlink…</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🌐 Navigating to Smartlinks…\n"
            "📝 Filling form…\n"
            "⏳ Submitting…\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            "<i>This may take 20–40 seconds.</i>"
        ),
    )

    result = await automation_create_smartlink()

    if result["success"]:
        url_line = (
            f"\n🔗 URL  : <code>{result['url']}</code>"
            if result.get("url")
            else "\n⚠️ URL could not be extracted — check dashboard."
        )
        text = (
            f"🎉 <b>Smartlink Created!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"📛 Name : <code>{result.get('name', 'N/A')}</code>"
            f"{url_line}\n"
            f"🕐 Time : {datetime.now().strftime('%H:%M:%S')}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
        )
        await notify_admin(
            context,
            f"🔗 <b>New Smartlink</b>\n"
            f"👤 <code>{SESSION.email}</code>\n"
            f"📛 <code>{result.get('name')}</code>\n"
            f"🔗 {result.get('url', 'N/A')}",
        )
    else:
        text = (
            f"❌ <b>Smartlink Creation Failed</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"⚠️ {result['message']}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
        )

    await safe_edit(query, text, keyboard=main_menu(SESSION.logged_in))
    return ConversationHandler.END


async def inline_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    status_icon = "🟢 Active"    if SESSION.logged_in    else "🔴 Inactive"
    browser_st  = "🟢 Running"   if SESSION.browser_alive else "⚫ Closed"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"

    text = (
        f"<b>📊 Live Session Status</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔐 Login   : {status_icon}\n"
        f"👤 Account : {account}\n"
        f"🌐 Browser : {browser_st}\n"
        f"🕐 Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await safe_edit(query, text, keyboard=main_menu(SESSION.logged_in))
    return ConversationHandler.END


# ================================================================
#                     ERROR HANDLER
# ================================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception: %s", context.error, exc_info=context.error)


# ================================================================
#                          MAIN
# ================================================================
def main() -> None:
    logger.info("=" * 60)
    logger.info("  ADSTERRA AUTOMATION BOT — Starting Up")
    logger.info("=" * 60)
    logger.info("Token    : %s…", TELEGRAM_BOT_TOKEN[:12])
    logger.info("Chat ID  : %s",  TELEGRAM_CHAT_ID)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Login Conversation ────────────────────────────────────
    login_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(conv_ask_email, pattern="^login$"),
        ],
        states={
            STATE_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, conv_receive_email),
            ],
            STATE_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, conv_receive_password),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Logout Conversation ───────────────────────────────────
    logout_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(conv_ask_logout, pattern="^logout$"),
        ],
        states={
            STATE_LOGOUT_CONFIRM: [
                CallbackQueryHandler(conv_logout_confirmed, pattern="^logout_confirm$"),
                CallbackQueryHandler(conv_logout_cancelled, pattern="^logout_cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Inline Actions (no conversation needed) ───────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(login_conv)
    app.add_handler(logout_conv)
    app.add_handler(CallbackQueryHandler(inline_create_smartlink, pattern="^create_smartlink$"))
    app.add_handler(CallbackQueryHandler(inline_status,           pattern="^status$"))
    app.add_error_handler(error_handler)

    logger.info("✅ Bot is live! Open Telegram and send /start")
    logger.info("=" * 60)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
