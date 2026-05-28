#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║        ADSTERRA AUTOMATION BOT - GOD LEVEL EDITION              ║
║         Login + Sign Up + Email Confirmation via Telegram        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import random
import logging
import sys
import re
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

ADSTERRA_LOGIN_URL:    str = "https://publishers.adsterra.com/login"
ADSTERRA_SIGNUP_URL:   str = "https://publishers.adsterra.com/register"
ADSTERRA_SMARTLINK_URL: str = "https://publishers.adsterra.com/smartlink"

# ================================================================
#                   CONVERSATION STATES
# ================================================================
(
    # Login flow
    STATE_LOGIN_EMAIL,
    STATE_LOGIN_PASSWORD,

    # Signup flow
    STATE_SIGNUP_NAME,
    STATE_SIGNUP_EMAIL,
    STATE_SIGNUP_PASSWORD,
    STATE_SIGNUP_WEBSITE,

    # Confirmation flow
    STATE_CONFIRM_LINK,

    # Logout flow
    STATE_LOGOUT_CONFIRM,

    # Post-confirm re-login
    STATE_RELOGIN_PASSWORD,

) = range(9)

# ================================================================
#                      SESSION STORE
# ================================================================
class SessionStore:
    """
    Holds all runtime state for one user session.
    Fully resettable via logout.
    """

    def __init__(self) -> None:
        # Credentials
        self.email:     Optional[str] = None
        self.password:  Optional[str] = None
        self.full_name: Optional[str] = None
        self.website:   Optional[str] = None

        # State flags
        self.logged_in:         bool = False
        self.signup_done:       bool = False
        self.awaiting_confirm:  bool = False

        # Browser
        self.page:    Optional[Page]           = None
        self.browser: Optional[Browser]        = None
        self.ctx:     Optional[BrowserContext] = None
        self._playwright                       = None
        self._lock = asyncio.Lock()

    # ── Properties ───────────────────────────────────────────
    @property
    def has_credentials(self) -> bool:
        return bool(self.email and self.password)

    @property
    def browser_alive(self) -> bool:
        return self.browser is not None

    # ── Full Logout ───────────────────────────────────────────
    async def full_logout(self) -> None:
        async with self._lock:
            self.email            = None
            self.password         = None
            self.full_name        = None
            self.website          = None
            self.logged_in        = False
            self.signup_done      = False
            self.awaiting_confirm = False
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
    Object.defineProperty(navigator, 'webdriver',
        { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',
        { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages',
        { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency',
        { get: () => 4 });
    window.chrome = { runtime: {} };
"""


async def human_delay(min_s: float = 1.2, max_s: float = 4.0) -> None:
    delay = random.uniform(min_s, max_s)
    logger.debug("💤 Delay %.2fs", delay)
    await asyncio.sleep(delay)


async def human_type(page: Page, selector: str, text: str) -> None:
    await page.click(selector)
    await human_delay(0.2, 0.6)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(40, 110))
    await human_delay(0.3, 0.7)


# ================================================================
#                  KEYBOARD FACTORY
# ================================================================
def main_menu(logged_in: bool = False) -> InlineKeyboardMarkup:
    if logged_in:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Create Smartlink", callback_data="create_smartlink")],
            [InlineKeyboardButton("📊 Session Status",   callback_data="status")],
            [InlineKeyboardButton("🚪 Logout",           callback_data="logout")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login",   callback_data="login")],
        [InlineKeyboardButton("📝 Sign Up", callback_data="signup")],
        [InlineKeyboardButton("📊 Status",  callback_data="status")],
    ])


CONFIRM_LOGOUT_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Yes, Logout", callback_data="logout_confirm"),
        InlineKeyboardButton("❌ Cancel",       callback_data="logout_cancel"),
    ]
])

# ================================================================
#                  TELEGRAM UTILITIES
# ================================================================
async def safe_edit(query, text: str, keyboard=None) -> None:
    kwargs = {"text": text, "parse_mode": "HTML"}
    if keyboard:
        kwargs["reply_markup"] = keyboard
    try:
        await query.edit_message_text(**kwargs)
    except Exception as exc:
        logger.warning("safe_edit failed: %s", exc)


async def safe_reply(update: Update, text: str, keyboard=None) -> None:
    kwargs = {"text": text, "parse_mode": "HTML"}
    if keyboard:
        kwargs["reply_markup"] = keyboard
    if update.message:
        await update.message.reply_text(**kwargs)
    elif update.callback_query:
        await update.callback_query.edit_message_text(**kwargs)


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("Admin notify failed: %s", exc)


async def delete_message(update: Update) -> None:
    try:
        await update.message.delete()
    except Exception:
        pass


# ================================================================
#                  PLAYWRIGHT ENGINE
# ================================================================
async def get_page() -> Page:
    """Return existing page or launch fresh browser."""
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
#              CORE AUTOMATION — SIGN UP
# ================================================================
async def automation_signup() -> dict:
    """
    Automate Adsterra publisher registration.
    Returns {"success": bool, "message": str, "needs_confirm": bool}
    """
    try:
        page = await get_page()
        logger.info("📝 Navigating to signup page…")
        await page.goto(ADSTERRA_SIGNUP_URL, wait_until="networkidle")
        await human_delay(2.0, 4.0)

        # ── Full Name ─────────────────────────────────────────
        name_selectors = [
            'input[name="name"]',
            'input[name="full_name"]',
            'input[name="fullName"]',
            'input[placeholder*="name" i]',
            'input[placeholder*="full" i]',
        ]
        for sel in name_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.full_name)
                    logger.info("👤 Name filled")
                    break
            except Exception:
                continue

        await human_delay(0.8, 1.5)

        # ── Email ─────────────────────────────────────────────
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="email" i]',
        ]
        for sel in email_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.email)
                    logger.info("📧 Email filled")
                    break
            except Exception:
                continue

        await human_delay(0.8, 1.5)

        # ── Password ──────────────────────────────────────────
        pass_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="password" i]',
        ]
        for sel in pass_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.password)
                    logger.info("🔑 Password filled")
                    break
            except Exception:
                continue

        await human_delay(0.8, 1.5)

        # ── Confirm Password (if present) ─────────────────────
        confirm_selectors = [
            'input[name="password_confirmation"]',
            'input[name="confirm_password"]',
            'input[name="confirmPassword"]',
            'input[placeholder*="confirm" i]',
            'input[placeholder*="repeat" i]',
        ]
        for sel in confirm_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.password)
                    logger.info("🔑 Confirm password filled")
                    break
            except Exception:
                continue

        await human_delay(0.8, 1.5)

        # ── Website (if present) ──────────────────────────────
        if SESSION.website:
            website_selectors = [
                'input[name="website"]',
                'input[name="site_url"]',
                'input[name="url"]',
                'input[placeholder*="website" i]',
                'input[placeholder*="url" i]',
            ]
            for sel in website_selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        await human_type(page, sel, SESSION.website)
                        logger.info("🌐 Website filled")
                        break
                except Exception:
                    continue

        await human_delay(1.0, 2.0)

        # ── Accept Terms Checkbox (if present) ────────────────
        checkbox_selectors = [
            'input[type="checkbox"][name*="agree" i]',
            'input[type="checkbox"][name*="terms" i]',
            'input[type="checkbox"][id*="agree" i]',
            'input[type="checkbox"][id*="terms" i]',
            'input[type="checkbox"]',
        ]
        for sel in checkbox_selectors:
            try:
                cb = page.locator(sel).first
                if await cb.count() > 0:
                    is_checked = await cb.is_checked()
                    if not is_checked:
                        await cb.check()
                        logger.info("☑️  Terms checkbox checked")
                    break
            except Exception:
                continue

        await human_delay(1.0, 2.0)

        # ── Submit ────────────────────────────────────────────
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Register")',
            'button:has-text("Sign Up")',
            'button:has-text("Create Account")',
            'button:has-text("Join")',
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
            return {
                "success": False,
                "message": "Submit button not found on signup page.",
                "needs_confirm": False,
            }

        await page.wait_for_load_state("networkidle")
        await human_delay(4.0, 7.0)

        current_url = page.url.lower()
        logger.info("📍 Post-signup URL: %s", current_url)

        # ── Detect confirmation required ──────────────────────
        confirm_signals = [
            "confirm"      in current_url,
            "verify"       in current_url,
            "verification" in current_url,
            "check"        in current_url,
            await page.locator("text=confirm").count() > 0,
            await page.locator("text=verify").count() > 0,
            await page.locator("text=Check your email").count() > 0,
            await page.locator("text=confirmation email").count() > 0,
            await page.locator("text=activation").count() > 0,
        ]

        # ── Detect success without confirmation ───────────────
        success_signals = [
            "dashboard" in current_url,
            "publisher" in current_url,
            await page.locator("text=Dashboard").count() > 0,
        ]

        # ── Detect errors ─────────────────────────────────────
        error_selectors = [
            ".alert-danger", ".error-message",
            "[class*='error']", "p.text-red",
        ]
        for sel in error_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    err = (await el.first.inner_text()).strip()
                    if err:
                        return {
                            "success": False,
                            "message": f"Signup error: {err}",
                            "needs_confirm": False,
                        }
            except Exception:
                continue

        if any(confirm_signals):
            SESSION.signup_done      = True
            SESSION.awaiting_confirm = True
            return {
                "success": True,
                "message": "Signup successful! Confirmation email sent.",
                "needs_confirm": True,
            }

        if any(success_signals):
            SESSION.signup_done = True
            SESSION.logged_in   = True
            return {
                "success": True,
                "message": "Signup successful! Logged in directly.",
                "needs_confirm": False,
            }

        return {
            "success": False,
            "message": "Signup outcome unclear. Check your email or try again.",
            "needs_confirm": False,
        }

    except Exception as exc:
        logger.exception("Signup exception")
        return {
            "success": False,
            "message": f"Unexpected error: {exc}",
            "needs_confirm": False,
        }


# ================================================================
#           CORE AUTOMATION — OPEN CONFIRMATION LINK
# ================================================================
async def automation_open_confirmation(confirm_url: str) -> dict:
    """
    Navigate to the confirmation link in the existing browser session.
    Returns {"success": bool, "message": str}
    """
    try:
        page = await get_page()
        logger.info("🔗 Opening confirmation link: %s", confirm_url)

        await page.goto(confirm_url, wait_until="networkidle")
        await human_delay(3.0, 6.0)

        current_url = page.url.lower()
        page_text   = (await page.inner_text("body")).lower()
        logger.info("📍 Post-confirm URL: %s", current_url)

        success_signals = [
            "dashboard"     in current_url,
            "publisher"     in current_url,
            "verified"      in current_url,
            "confirmed"     in current_url,
            "success"       in current_url,
            "verified"      in page_text,
            "confirmed"     in page_text,
            "congratulation" in page_text,
            "successfully"  in page_text,
            await page.locator("text=Dashboard").count() > 0,
            await page.locator("text=verified").count() > 0,
        ]

        if any(success_signals):
            SESSION.awaiting_confirm = False
            return {
                "success": True,
                "message": "Email confirmed successfully!",
            }

        # Check for already-confirmed or expiry
        if "expired" in page_text or "invalid" in page_text:
            return {
                "success": False,
                "message": "Confirmation link expired or invalid. Request a new one.",
            }

        return {
            "success": True,
            "message": "Confirmation link opened. Page may need login now.",
        }

    except Exception as exc:
        logger.exception("Confirmation exception")
        return {"success": False, "message": f"Error: {exc}"}


# ================================================================
#              CORE AUTOMATION — LOGIN
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

        # ── Email ─────────────────────────────────────────────
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
                    logger.info("📧 Email filled")
                    break
            except Exception:
                continue

        if not email_filled:
            return {"success": False, "message": "Email field not found."}

        await human_delay(0.8, 1.5)

        # ── Password ──────────────────────────────────────────
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
                    logger.info("🔑 Password filled")
                    break
            except Exception:
                continue

        if not pass_filled:
            return {"success": False, "message": "Password field not found."}

        await human_delay(1.0, 2.0)

        # ── Submit ────────────────────────────────────────────
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
        ]
        for sel in submit_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    logger.info("🖱️  Submitted login")
                    break
            except Exception:
                continue

        await page.wait_for_load_state("networkidle")
        await human_delay(4.0, 7.0)

        current_url = page.url.lower()
        logger.info("📍 Post-login URL: %s", current_url)

        success_signals = [
            "dashboard" in current_url,
            "publisher" in current_url,
            "smartlink" in current_url,
            "/home"     in current_url,
            await page.locator("text=Dashboard").count() > 0,
            await page.locator("text=Smartlink").count() > 0,
            await page.locator("text=Log out").count()  > 0,
        ]

        if any(success_signals):
            SESSION.logged_in = True
            return {"success": True, "message": "Login successful"}

        # ── Error on page ─────────────────────────────────────
        for sel in [".alert-danger", ".error-message", "[class*='error']"]:
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
            "message": "Login failed — wrong credentials, 2FA, or CAPTCHA.",
        }

    except Exception as exc:
        logger.exception("Login exception")
        return {"success": False, "message": f"Unexpected error: {exc}"}


# ================================================================
#              CORE AUTOMATION — CREATE SMARTLINK
# ================================================================
async def automation_create_smartlink() -> dict:
    try:
        page = await get_page()
        logger.info("🔗 Navigating to Smartlinks…")
        await page.goto(ADSTERRA_SMARTLINK_URL, wait_until="networkidle")
        await human_delay(3.0, 5.5)

        create_selectors = [
            "text=Create Smartlink", "text=New Smartlink",
            "button:has-text('Create')", "a:has-text('Create')",
        ]
        clicked = False
        for sel in create_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            return {
                "success": False,
                "message": "Create Smartlink button not found.",
                "url": None, "name": None,
            }

        await human_delay(2.5, 4.5)
        smartlink_name = f"AutoLink_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for sel in ['input[name="name"]', 'input[placeholder*="name" i]']:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, smartlink_name)
                    break
            except Exception:
                continue

        await human_delay(1.0, 2.0)

        for sel in ['select[name="category"]', 'select[name="vertical"]']:
            try:
                if await page.locator(sel).count() > 0:
                    await page.select_option(sel, index=1)
                    await human_delay(1.0, 2.0)
                    break
            except Exception:
                continue

        for sel in ['button[type="submit"]', "text=Create", "text=Save"]:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    break
            except Exception:
                continue

        await human_delay(5.0, 9.0)

        for sel in ["input[value^='https://']", "input[value^='http://']"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    url = await el.input_value()
                    if url.startswith("http"):
                        return {
                            "success": True,
                            "message": "Smartlink created!",
                            "url": url, "name": smartlink_name,
                        }
            except Exception:
                continue

        return {
            "success": True,
            "message": "Smartlink likely created. Check dashboard for URL.",
            "url": None, "name": smartlink_name,
        }

    except Exception as exc:
        logger.exception("Smartlink exception")
        return {"success": False, "message": str(exc), "url": None, "name": None}


# ================================================================
#                  COMMAND — /start
# ================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user        = update.effective_user
    now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "🟢 Active" if SESSION.logged_in else "🔴 Not logged in"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"
    confirm_row = ""
    if SESSION.awaiting_confirm:
        confirm_row = "\n⚠️ Awaiting email confirmation!\n"

    text = (
        f"👋 <b>Hello, {user.first_name}!</b>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🤖 <b>Adsterra Automation Bot</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"📌 Session : {status_icon}\n"
        f"👤 Account : {account}\n"
        f"🕐 Time    : {now}"
        f"{confirm_row}\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"Choose an option below 👇"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )


# ================================================================
#                  COMMAND — /status
# ================================================================
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_icon = "🟢 Active"  if SESSION.logged_in    else "🔴 Inactive"
    browser_st  = "🟢 Running" if SESSION.browser_alive else "⚫ Closed"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"
    confirm_st  = "⚠️ Awaiting" if SESSION.awaiting_confirm else "✅ Done"

    text = (
        f"<b>📊 Live Session Report</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔐 Login       : {status_icon}\n"
        f"👤 Account     : {account}\n"
        f"🌐 Browser     : {browser_st}\n"
        f"📧 Confirmed   : {confirm_st}\n"
        f"🕐 Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )


# ================================================================
#                  COMMAND — /cancel
# ================================================================
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ <b>Operation cancelled.</b>",
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#              CONVERSATION — LOGIN FLOW
# ================================================================
async def login_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if SESSION.logged_in:
        await safe_edit(
            query,
            (
                f"✅ <b>Already logged in!</b>\n\n"
                f"👤 <code>{SESSION.email}</code>\n\n"
                f"Use 🚪 <b>Logout</b> to switch accounts."
            ),
            keyboard=main_menu(True),
        )
        return ConversationHandler.END

    await safe_edit(
        query,
        (
            "🔐 <b>Adsterra Login</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "📧 <b>Step 1 / 2</b> — Email\n\n"
            "Send your <b>Adsterra email address</b>:\n\n"
            "<i>/cancel to abort</i>"
        ),
    )
    return STATE_LOGIN_EMAIL


async def login_receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "⚠️ Invalid email. Try again:",
            parse_mode="HTML",
        )
        return STATE_LOGIN_EMAIL

    SESSION.email = email
    await delete_message(update)

    await update.message.reply_text(
        (
            "✅ <b>Email received!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🔑 <b>Step 2 / 2</b> — Password\n\n"
            "Send your <b>password</b>:\n\n"
            "<i>Deleted instantly for security. /cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_LOGIN_PASSWORD


async def login_receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    SESSION.password = update.message.text.strip()
    await delete_message(update)

    msg = await update.message.reply_text(
        (
            "⏳ <b>Logging in…</b>\n\n"
            "🌐 Launching browser…\n"
            "🔑 Filling credentials…\n"
            "⏳ Awaiting response…\n\n"
            "<i>Takes 15–30 seconds…</i>"
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
            f"Ready! Use 🔗 Create Smartlink 🎉"
        )
        await notify_admin(
            context,
            f"🟢 <b>Login</b>\n👤 <code>{SESSION.email}</code>\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        )
    else:
        SESSION.email    = None
        SESSION.password = None
        text = (
            f"❌ <b>Login Failed</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"⚠️ {result['message']}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"Please try again."
        )

    await msg.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#              CONVERSATION — SIGN UP FLOW
# ================================================================
async def signup_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if SESSION.logged_in:
        await safe_edit(
            query,
            "✅ Already logged in. Logout first to create a new account.",
            keyboard=main_menu(True),
        )
        return ConversationHandler.END

    await safe_edit(
        query,
        (
            "📝 <b>Adsterra Sign Up</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "👤 <b>Step 1 / 4</b> — Full Name\n\n"
            "Send your <b>full name</b>:\n\n"
            "<i>/cancel to abort</i>"
        ),
    )
    return STATE_SIGNUP_NAME


async def signup_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("⚠️ Name too short. Try again:")
        return STATE_SIGNUP_NAME

    SESSION.full_name = name
    await update.message.reply_text(
        (
            "✅ <b>Name saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "📧 <b>Step 2 / 4</b> — Email\n\n"
            "Send your <b>email address</b>:\n\n"
            "<i>/cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_SIGNUP_EMAIL


async def signup_receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("⚠️ Invalid email. Try again:")
        return STATE_SIGNUP_EMAIL

    SESSION.email = email
    await delete_message(update)

    await update.message.reply_text(
        (
            "✅ <b>Email saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🔑 <b>Step 3 / 4</b> — Password\n\n"
            "Send your <b>desired password</b>:\n"
            "<i>Min 8 characters. Deleted instantly.\n"
            "/cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_SIGNUP_PASSWORD


async def signup_receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text.strip()
    await delete_message(update)

    if len(password) < 8:
        await update.message.reply_text(
            "⚠️ Password must be at least 8 characters. Try again:"
        )
        return STATE_SIGNUP_PASSWORD

    SESSION.password = password
    await update.message.reply_text(
        (
            "✅ <b>Password saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🌐 <b>Step 4 / 4</b> — Website\n\n"
            "Send your <b>website URL</b>\n"
            "<i>(or type <code>skip</code> to skip)\n"
            "/cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_SIGNUP_WEBSITE


async def signup_receive_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text.lower() == "skip":
        SESSION.website = None
    else:
        # Basic URL check
        if not text.startswith("http"):
            text = "https://" + text
        SESSION.website = text

    msg = await update.message.reply_text(
        (
            "⏳ <b>Creating your account…</b>\n\n"
            f"👤 Name     : {SESSION.full_name}\n"
            f"📧 Email    : <code>{SESSION.email}</code>\n"
            f"🌐 Website  : {SESSION.website or 'N/A'}\n\n"
            "🌐 Launching browser…\n"
            "📝 Filling signup form…\n"
            "⏳ Submitting…\n\n"
            "<i>Takes 20–40 seconds…</i>"
        ),
        parse_mode="HTML",
    )

    result = await automation_signup()

    if result["success"] and result["needs_confirm"]:
        # ── Needs email confirmation ──────────────────────────
        text_reply = (
            f"✅ <b>Account Created!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"📧 Email    : <code>{SESSION.email}</code>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"📬 <b>Confirmation email sent!</b>\n\n"
            f"Please:\n"
            f"1️⃣  Check your inbox for <b>{SESSION.email}</b>\n"
            f"2️⃣  Open the confirmation email\n"
            f"3️⃣  <b>Copy the confirmation link</b>\n"
            f"4️⃣  Send it here in this chat\n\n"
            f"<i>The link will be opened in the same browser session.\n"
            f"After confirmation the page may ask you to login again — "
            f"the bot will handle that automatically!</i>"
        )
        await msg.edit_text(text_reply, parse_mode="HTML")
        await notify_admin(
            context,
            f"📝 <b>New Signup</b>\n👤 {SESSION.full_name}\n"
            f"📧 <code>{SESSION.email}</code>\n"
            f"⏳ Awaiting email confirmation",
        )
        return STATE_CONFIRM_LINK

    elif result["success"] and not result["needs_confirm"]:
        # ── Directly logged in after signup ───────────────────
        text_reply = (
            f"🎉 <b>Account Created & Logged In!</b>\n\n"
            f"👤 <code>{SESSION.email}</code>\n\n"
            f"You can now create Smartlinks!"
        )
        await msg.edit_text(
            text_reply,
            parse_mode="HTML",
            reply_markup=main_menu(True),
        )
        return ConversationHandler.END

    else:
        # ── Signup failed ─────────────────────────────────────
        SESSION.email    = None
        SESSION.password = None
        SESSION.full_name = None
        text_reply = (
            f"❌ <b>Signup Failed</b>\n\n"
            f"⚠️ {result['message']}\n\n"
            f"Please try again."
        )
        await msg.edit_text(
            text_reply,
            parse_mode="HTML",
            reply_markup=main_menu(False),
        )
        return ConversationHandler.END


# ================================================================
#          CONVERSATION — EMAIL CONFIRMATION LINK
# ================================================================
async def confirm_receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    User pastes the confirmation link from their email.
    Bot opens it in the same browser session,
    then automatically logs in again.
    """
    raw = update.message.text.strip()

    # ── Extract URL from text ─────────────────────────────────
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, raw)
    confirm_url = urls[0] if urls else raw

    if not confirm_url.startswith("http"):
        await update.message.reply_text(
            "⚠️ <b>That doesn't look like a valid URL.</b>\n\n"
            "Please send the full confirmation link from your email.\n"
            "<i>It should start with https://</i>",
            parse_mode="HTML",
        )
        return STATE_CONFIRM_LINK

    msg = await update.message.reply_text(
        (
            "⏳ <b>Opening confirmation link…</b>\n\n"
            f"🔗 <code>{confirm_url[:60]}{'…' if len(confirm_url) > 60 else ''}</code>\n\n"
            "🌐 Loading in browser…\n"
            "✅ Verifying your account…\n\n"
            "<i>Please wait…</i>"
        ),
        parse_mode="HTML",
    )

    result = await automation_open_confirmation(confirm_url)

    if result["success"]:
        # ── Auto re-login after confirmation ──────────────────
        await msg.edit_text(
            (
                "✅ <b>Confirmation Link Opened!</b>\n\n"
                "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                "🔄 <b>Auto-logging in now…</b>\n"
                "🔑 Using your saved credentials…\n"
                "<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                "<i>Takes 15–20 seconds…</i>"
            ),
            parse_mode="HTML",
        )

        # Small delay to let the confirmation settle
        await human_delay(2.0, 4.0)

        # ── Destroy old browser session & login fresh ─────────
        await SESSION._destroy_browser()
        login_result = await automation_login()

        if login_result["success"]:
            final_text = (
                f"🎉 <b>Account Confirmed & Logged In!</b>\n\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"👤 Account : <code>{SESSION.email}</code>\n"
                f"🕐 Time    : {datetime.now().strftime('%H:%M:%S')}\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                f"✅ Your account is fully active!\n"
                f"Use 🔗 <b>Create Smartlink</b> to begin! 🎉"
            )
            await notify_admin(
                context,
                f"🎉 <b>Account Confirmed + Logged In</b>\n"
                f"👤 <code>{SESSION.email}</code>\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            )
            await msg.edit_text(
                final_text,
                parse_mode="HTML",
                reply_markup=main_menu(True),
            )
            return ConversationHandler.END

        else:
            # ── Auto-login failed, ask password again ─────────
            await msg.edit_text(
                (
                    "✅ <b>Email Confirmed!</b>\n\n"
                    "⚠️ Auto-login failed. Please re-enter your password:\n\n"
                    "<i>Deleted instantly for security. /cancel to abort</i>"
                ),
                parse_mode="HTML",
            )
            return STATE_RELOGIN_PASSWORD

    else:
        await msg.edit_text(
            (
                f"❌ <b>Confirmation Failed</b>\n\n"
                f"⚠️ {result['message']}\n\n"
                f"Please send the correct confirmation link, or use /start."
            ),
            parse_mode="HTML",
            reply_markup=main_menu(False),
        )
        return STATE_CONFIRM_LINK


# ================================================================
#          CONVERSATION — RE-LOGIN AFTER CONFIRMATION
# ================================================================
async def relogin_receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    If auto-login failed after confirmation,
    user sends password manually one more time.
    """
    SESSION.password = update.message.text.strip()
    await delete_message(update)

    msg = await update.message.reply_text(
        "⏳ <b>Logging in…</b> Please wait.",
        parse_mode="HTML",
    )

    # Destroy browser first, start fresh
    await SESSION._destroy_browser()
    result = await automation_login()

    if result["success"]:
        text = (
            f"✅ <b>Logged In Successfully!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 Account : <code>{SESSION.email}</code>\n"
            f"🕐 Time    : {datetime.now().strftime('%H:%M:%S')}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"Use 🔗 Create Smartlink to begin!"
        )
        await notify_admin(
            context,
            f"🟢 <b>Re-Login Success</b>\n👤 <code>{SESSION.email}</code>",
        )
    else:
        SESSION.password = None
        text = (
            f"❌ <b>Login Failed</b>\n\n"
            f"⚠️ {result['message']}\n\n"
            f"Use /start to try again."
        )

    await msg.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#              CONVERSATION — LOGOUT FLOW
# ================================================================
async def logout_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
            f"  🗑️  Clear credentials\n"
            f"  🌐  Close browser session\n"
            f"  🔐  End Adsterra session\n\n"
            f"<b>Are you sure?</b>"
        ),
        keyboard=CONFIRM_LOGOUT_KB,
    )
    return STATE_LOGOUT_CONFIRM


async def logout_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    old_email = SESSION.email or "Unknown"

    await safe_edit(query, "⏳ <b>Logging out…</b> Closing sessions…")
    await SESSION.full_logout()

    await safe_edit(
        query,
        (
            f"✅ <b>Logged Out!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 Account  : <code>{old_email}</code>\n"
            f"🕐 Time     : {datetime.now().strftime('%H:%M:%S')}\n"
            f"🌐 Browser  : Closed\n"
            f"🔐 Session  : Cleared\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"Use 🔐 Login or 📝 Sign Up to continue."
        ),
        keyboard=main_menu(False),
    )
    await notify_admin(
        context,
        f"🔴 <b>Logout</b>\n👤 <code>{old_email}</code>\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    )
    return ConversationHandler.END


async def logout_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await safe_edit(
        query,
        "✅ <b>Logout cancelled.</b> Session still active.",
        keyboard=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#              INLINE — CREATE SMARTLINK
# ================================================================
async def inline_create_smartlink(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    if not SESSION.logged_in:
        await safe_edit(
            query,
            "🔴 <b>Not logged in!</b> Please login first.",
            keyboard=main_menu(False),
        )
        return ConversationHandler.END

    await safe_edit(
        query,
        (
            "⏳ <b>Creating Smartlink…</b>\n\n"
            "🌐 Navigating…\n"
            "📝 Filling form…\n"
            "⏳ Submitting…\n\n"
            "<i>Takes 20–40 seconds…</i>"
        ),
    )

    result = await automation_create_smartlink()

    if result["success"]:
        url_line = (
            f"\n🔗 URL  : <code>{result['url']}</code>"
            if result.get("url")
            else "\n⚠️ URL not extracted — check dashboard."
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
            f"🔗 <b>Smartlink Created</b>\n👤 <code>{SESSION.email}</code>\n"
            f"📛 <code>{result.get('name')}</code>\n🔗 {result.get('url', 'N/A')}",
        )
    else:
        text = (
            f"❌ <b>Smartlink Failed</b>\n\n"
            f"⚠️ {result['message']}"
        )

    await safe_edit(query, text, keyboard=main_menu(SESSION.logged_in))
    return ConversationHandler.END


# ================================================================
#              INLINE — STATUS
# ================================================================
async def inline_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    status_icon = "🟢 Active"  if SESSION.logged_in    else "🔴 Inactive"
    browser_st  = "🟢 Running" if SESSION.browser_alive else "⚫ Closed"
    confirm_st  = "⚠️ Pending" if SESSION.awaiting_confirm else "✅ Done"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"

    text = (
        f"<b>📊 Live Session Status</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔐 Login     : {status_icon}\n"
        f"👤 Account   : {account}\n"
        f"🌐 Browser   : {browser_st}\n"
        f"📧 Confirmed : {confirm_st}\n"
        f"🕐 Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await safe_edit(query, text, keyboard=main_menu(SESSION.logged_in))
    return ConversationHandler.END


# ================================================================
#                     ERROR HANDLER
# ================================================================
async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.error("Unhandled exception: %s", context.error, exc_info=context.error)


# ================================================================
#                          MAIN
# ================================================================
def main() -> None:
    logger.info("=" * 60)
    logger.info("  ADSTERRA BOT — God Level Edition")
    logger.info("  Login | Sign Up | Confirmation | Logout")
    logger.info("=" * 60)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Login Conversation ────────────────────────────────────
    login_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(login_entry, pattern="^login$")],
        states={
            STATE_LOGIN_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_receive_email)
            ],
            STATE_LOGIN_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_receive_password)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Sign Up Conversation (includes confirmation + re-login)
    signup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(signup_entry, pattern="^signup$")],
        states={
            STATE_SIGNUP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, signup_receive_name)
            ],
            STATE_SIGNUP_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, signup_receive_email)
            ],
            STATE_SIGNUP_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, signup_receive_password)
            ],
            STATE_SIGNUP_WEBSITE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, signup_receive_website)
            ],
            # ← User pastes confirmation link here
            STATE_CONFIRM_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_receive_link)
            ],
            # ← If auto-login fails after confirmation
            STATE_RELOGIN_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, relogin_receive_password)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Logout Conversation ───────────────────────────────────
    logout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(logout_entry, pattern="^logout$")],
        states={
            STATE_LOGOUT_CONFIRM: [
                CallbackQueryHandler(logout_confirmed, pattern="^logout_confirm$"),
                CallbackQueryHandler(logout_cancelled, pattern="^logout_cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Register all handlers ─────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(login_conv)
    app.add_handler(signup_conv)
    app.add_handler(logout_conv)
    app.add_handler(
        CallbackQueryHandler(inline_create_smartlink, pattern="^create_smartlink$")
    )
    app.add_handler(CallbackQueryHandler(inline_status, pattern="^status$"))
    app.add_error_handler(error_handler)

    logger.info("✅ Bot is live! Send /start in Telegram.")
    logger.info("=" * 60)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
