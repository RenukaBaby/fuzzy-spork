#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║     ADSTERRA BETA PUBLISHER BOT - REAL FIELD SELECTORS          ║
║     Handles: Cloudflare Turnstile + Real Form Automation        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import random
import logging
import sys
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters,
)

# ================================================================
#                        LOGGING
# ================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AdsterraBot")

# ================================================================
#                        CONFIG
# ================================================================
TELEGRAM_BOT_TOKEN = "8766573450:AAGDkv16RZOKPb8jqEZTGVoO5SsjmYnK6zI"
TELEGRAM_CHAT_ID   = "3797306274"

SIGNUP_URL    = "https://beta.publishers.adsterra.com/signup"
LOGIN_URL     = "https://beta.publishers.adsterra.com/login"
DASHBOARD_URL = "https://beta.publishers.adsterra.com/dashboard"

# ================================================================
#                  CONVERSATION STATES
# ================================================================
(
    STATE_LOGIN_EMAIL,
    STATE_LOGIN_PASSWORD,
    STATE_SIGNUP_CONFIRM,
    STATE_CONFIRM_LINK,
    STATE_RELOGIN_PASSWORD,
    STATE_LOGOUT_CONFIRM,
    STATE_MANUAL_NAME,
    STATE_MANUAL_EMAIL,
    STATE_MANUAL_LOGIN,
    STATE_MANUAL_PASSWORD,
    STATE_MANUAL_MESSENGER,
    STATE_MANUAL_MESSENGER_ACCOUNT,
    STATE_MANUAL_COUNTRY,
    STATE_TURNSTILE_TOKEN,
) = range(14)

# ================================================================
#                  TEST DATA BANK
# ================================================================
FIRST_NAMES = [
    "James", "Oliver", "William", "Benjamin", "Lucas",
    "Henry", "Alexander", "Mason", "Ethan", "Daniel",
    "Emma", "Sophia", "Isabella", "Mia", "Charlotte",
    "Amelia", "Harper", "Evelyn", "Abigail", "Emily",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Wilson", "Anderson",
    "Taylor", "Moore", "Jackson", "Martin", "Lee",
    "Thompson", "White", "Harris", "Clark", "Lewis",
]

COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Australia",
    "Germany", "France", "Netherlands", "Sweden", "Spain",
    "Italy", "Poland", "Brazil", "Mexico", "India",
    "Indonesia", "Pakistan", "Turkey", "Argentina",
]

MESSENGERS = ["Telegram", "Skype", "WhatsApp"]

TEST_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com",
    "protonmail.com", "icloud.com", "mail.com",
]

# ================================================================
#                  PROFILE GENERATOR
# ================================================================
@dataclass
class Profile:
    full_name:         str = ""
    email:             str = ""
    login:             str = ""
    password:          str = ""
    messenger:         str = "Telegram"
    messenger_account: str = ""
    country:           str = "United States"


class Generator:
    @staticmethod
    def make() -> Profile:
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)
        num   = random.randint(100, 9999)

        full_name = f"{first} {last}"
        email     = f"{first.lower()}.{last.lower()}{num}@{random.choice(TEST_DOMAINS)}"
        login     = f"{first.lower()}{last.lower()}{num}"

        words    = ["Phoenix", "Storm", "Tiger", "Eagle", "Wolf", "Falcon", "Knight", "Dragon"]
        password = (
            f"{random.choice(words)}"
            f"{random.randint(10, 99)}"
            f"{random.choice(['!', '@', '#', '$'])}"
            f"{random.choice(words)}"
            f"{random.randint(10, 99)}"
        )

        messenger         = random.choice(MESSENGERS)
        messenger_account = f"@{first.lower()}{last.lower()[0]}{num}"
        country           = random.choice(COUNTRIES)

        return Profile(
            full_name         = full_name,
            email             = email,
            login             = login,
            password          = password,
            messenger         = messenger,
            messenger_account = messenger_account,
            country           = country,
        )

# ================================================================
#                  SESSION STORE
# ================================================================
@dataclass
class Session:
    email:            Optional[str]     = None
    password:         Optional[str]     = None
    login:            Optional[str]     = None
    profile:          Optional[Profile] = None
    logged_in:        bool              = False
    awaiting_confirm: bool              = False
    page:             Optional[Page]    = None
    browser:          Optional[Browser] = None
    ctx:              Optional[BrowserContext] = None
    _pw: object = None

    def __post_init__(self):
        self._lock = asyncio.Lock()

    @property
    def browser_alive(self) -> bool:
        return self.browser is not None

    async def reset(self):
        async with self._lock:
            self.email = self.password = self.login = None
            self.profile          = None
            self.logged_in        = False
            self.awaiting_confirm = False
            await self._close_browser()

    async def _close_browser(self):
        for obj in [self.page, self.ctx, self.browser]:
            if obj:
                try:
                    await obj.close()
                except Exception:
                    pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self.page = self.ctx = self.browser = self._pw = None


SES = Session()

# ================================================================
#                  PLAYWRIGHT — STEALTH MODE
# ================================================================
STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver',  { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',    { get: () => [1,2,3,4,5] });
    Object.defineProperty(navigator, 'languages',  { get: () => ['en-US','en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory',{ get: () => 8 });
    window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
    const orig = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() {
        return orig.apply(this, arguments);
    };
"""

async def get_page(headless: bool = True) -> Page:
    if SES.page and not SES.page.is_closed():
        return SES.page

    logger.info("🌐 Launching browser...")
    SES._pw = await async_playwright().start()

    SES.browser = await SES._pw.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--window-size=1366,768",
        ],
    )

    SES.ctx = await SES.browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    await SES.ctx.add_init_script(STEALTH_JS)
    SES.page = await SES.ctx.new_page()
    SES.page.set_default_timeout(60_000)
    return SES.page


async def human_delay(a: float = 0.8, b: float = 2.0):
    await asyncio.sleep(random.uniform(a, b))


async def human_type(page: Page, selector: str, text: str):
    await page.click(selector)
    await human_delay(0.2, 0.5)
    for ch in text:
        await page.keyboard.type(ch, delay=random.randint(50, 130))
    await human_delay(0.2, 0.5)


# ================================================================
#         REAL FIELD SELECTORS (from your screenshot)
# ================================================================
"""
Based on the actual signup page, the form uses Vuetify components.
Real selectors for Adsterra Beta Signup:
"""

SIGNUP_SELECTORS = {
    # ── Input fields (Vuetify wraps in .v-input) ──────────────
    "email":             'input[type="email"], input[autocomplete="email"]',
    "full_name":         'input[autocomplete="name"], label:has-text("First and Last Name") + input, .v-input:has(label:has-text("First and Last Name")) input',
    "login":             '.v-input:has(label:has-text("Login")) input',
    "password":          'input[type="password"], .v-input:has(label:has-text("Password")) input',
    "messenger_account": '.v-input:has(label:has-text("Messenger account")) input',

    # ── Dropdowns ─────────────────────────────────────────────
    "messenger":         '.v-select:has(label:has-text("Messenger"))',
    "country":           '.v-select:has(label:has-text("country")), .v-select:has(label:has-text("Country"))',

    # ── Checkbox ──────────────────────────────────────────────
    "terms":             'input[type="checkbox"]',

    # ── Submit ────────────────────────────────────────────────
    "submit":            'button:has-text("SIGN UP"), button:has-text("Sign Up")',
}

LOGIN_SELECTORS = {
    "email":    'input[type="email"], input[autocomplete="email"], input[autocomplete="username"]',
    "password": 'input[type="password"]',
    "submit":   'button:has-text("LOG IN"), button:has-text("Log In"), button[type="submit"]',
}

# ================================================================
#              CORE AUTOMATION — SIGN UP
# ================================================================
async def auto_signup(profile: Profile) -> dict:
    """
    Real Adsterra Beta signup automation.
    Handles Vuetify components + Cloudflare Turnstile.
    """
    try:
        page = await get_page(headless=True)
        logger.info("📝 Loading signup page...")
        await page.goto(SIGNUP_URL, wait_until="domcontentloaded")
        await human_delay(3.0, 5.0)
        await page.wait_for_load_state("networkidle", timeout=30_000)

        # ── 1. Email ──────────────────────────────────────────
        logger.info("📧 Filling email...")
        try:
            await page.locator(SIGNUP_SELECTORS["email"]).first.click()
            await human_delay()
            await page.keyboard.type(profile.email, delay=80)
            await human_delay(0.5, 1.0)
        except Exception as e:
            logger.error("Email fill failed: %s", e)
            return {"success": False, "message": f"Email field error: {e}"}

        # ── 2. Full Name ──────────────────────────────────────
        logger.info("👤 Filling name...")
        try:
            # Vuetify uses label wrapping
            name_input = page.locator('input').nth(1)  # 2nd input on page
            await name_input.click()
            await human_delay()
            await page.keyboard.type(profile.full_name, delay=80)
            await human_delay(0.5, 1.0)
        except Exception as e:
            logger.error("Name fill failed: %s", e)

        # ── 3. Login (username) ───────────────────────────────
        logger.info("🆔 Filling login...")
        try:
            login_input = page.locator('input').nth(2)
            await login_input.click()
            await human_delay()
            await page.keyboard.type(profile.login, delay=80)
            await human_delay(0.5, 1.0)
        except Exception as e:
            logger.error("Login fill failed: %s", e)

        # ── 4. Password ───────────────────────────────────────
        logger.info("🔑 Filling password...")
        try:
            pw_input = page.locator('input[type="password"]').first
            await pw_input.click()
            await human_delay()
            await page.keyboard.type(profile.password, delay=80)
            await human_delay(0.5, 1.0)
        except Exception as e:
            logger.error("Password fill failed: %s", e)

        # ── 5. Messenger Dropdown ─────────────────────────────
        logger.info("💬 Selecting messenger: %s", profile.messenger)
        try:
            # Click the messenger dropdown
            messenger_dd = page.locator('.v-select').nth(0)
            await messenger_dd.click()
            await human_delay(1.0, 2.0)

            # Click the option in the dropdown menu
            option = page.locator(f'.v-list-item:has-text("{profile.messenger}")').first
            if await option.count() > 0:
                await option.click()
                logger.info("✅ Messenger selected")
            await human_delay()
        except Exception as e:
            logger.error("Messenger select failed: %s", e)

        # ── 6. Messenger Account ──────────────────────────────
        logger.info("📱 Filling messenger account...")
        try:
            # Find input after messenger dropdown
            msg_inputs = await page.locator('input[type="text"]').all()
            if msg_inputs:
                # Find the messenger account input (last text input usually)
                for inp in msg_inputs:
                    placeholder = await inp.get_attribute("placeholder") or ""
                    aria        = await inp.get_attribute("aria-label")  or ""
                    if "messenger" in (placeholder + aria).lower() and "account" in (placeholder + aria).lower():
                        await inp.click()
                        await human_delay()
                        await page.keyboard.type(profile.messenger_account, delay=80)
                        break
                else:
                    # Fallback: try the 5th input
                    await page.locator('input').nth(4).click()
                    await human_delay()
                    await page.keyboard.type(profile.messenger_account, delay=80)
            await human_delay(0.5, 1.0)
        except Exception as e:
            logger.error("Messenger account fill failed: %s", e)

        # ── 7. Country Dropdown ───────────────────────────────
        logger.info("🌍 Selecting country: %s", profile.country)
        try:
            country_dd = page.locator('.v-select').nth(1)
            await country_dd.click()
            await human_delay(1.0, 2.0)

            # Type to search
            await page.keyboard.type(profile.country[:5], delay=100)
            await human_delay(1.0, 2.0)

            # Click matching option
            option = page.locator(f'.v-list-item:has-text("{profile.country}")').first
            if await option.count() > 0:
                await option.click()
                logger.info("✅ Country selected")
            else:
                # Just pick first option
                first_opt = page.locator('.v-list-item').first
                if await first_opt.count() > 0:
                    await first_opt.click()
            await human_delay()
        except Exception as e:
            logger.error("Country select failed: %s", e)

        # ── 8. CLOUDFLARE TURNSTILE ───────────────────────────
        logger.info("🛡️ Checking for Cloudflare Turnstile...")
        await human_delay(2.0, 4.0)

        try:
            # Look for Turnstile iframe
            turnstile_present = await page.locator('iframe[src*="challenges.cloudflare.com"]').count() > 0

            if turnstile_present:
                logger.info("⚠️ Cloudflare Turnstile detected!")
                logger.info("⏳ Waiting up to 30s for auto-solve...")

                # Wait for token to appear in DOM
                for i in range(30):
                    token = await page.evaluate("""() => {
                        const inputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
                        for (const inp of inputs) {
                            if (inp.value && inp.value.length > 20) return inp.value;
                        }
                        return null;
                    }""")
                    if token:
                        logger.info("✅ Turnstile solved! Token length: %d", len(token))
                        break
                    await asyncio.sleep(1)
                else:
                    logger.warning("⚠️ Turnstile NOT solved automatically.")
                    return {
                        "success": False,
                        "message": (
                            "🛡️ Cloudflare Turnstile blocked the signup.\n\n"
                            "This is the main blocker for automated signups.\n"
                            "Solutions:\n"
                            "• Use a CAPTCHA solver service (2Captcha, CapMonster)\n"
                            "• Run with headless=False on residential IP\n"
                            "• Sign up manually one time"
                        ),
                    }
            else:
                logger.info("✅ No Turnstile detected (or already solved)")
        except Exception as e:
            logger.warning("Turnstile check error: %s", e)

        # ── 9. Terms Checkbox ─────────────────────────────────
        logger.info("☑️ Checking terms...")
        try:
            checkbox = page.locator('input[type="checkbox"]').first
            if await checkbox.count() > 0:
                if not await checkbox.is_checked():
                    # Click parent label since Vuetify wraps checkbox
                    await page.locator('.v-checkbox, label:has(input[type="checkbox"])').first.click()
                    await human_delay()
                    logger.info("✅ Terms checked")
        except Exception as e:
            logger.error("Terms checkbox failed: %s", e)

        await human_delay(1.0, 2.0)

        # ── 10. Click SIGN UP ─────────────────────────────────
        logger.info("🚀 Clicking SIGN UP...")
        try:
            submit_btn = page.locator(SIGNUP_SELECTORS["submit"]).first
            await submit_btn.click()
            logger.info("✅ Submit clicked")
        except Exception as e:
            logger.error("Submit failed: %s", e)
            return {"success": False, "message": f"Submit error: {e}"}

        # ── 11. Wait for response ─────────────────────────────
        await human_delay(5.0, 8.0)
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass

        url_      = page.url.lower()
        page_text = (await page.inner_text("body")).lower()
        logger.info("📍 Post-submit URL: %s", url_)

        # ── 12. Detect outcome ────────────────────────────────
        if any(k in page_text for k in [
            "confirm your email", "verify your email",
            "check your email", "confirmation email",
            "sent to your email", "activate your account",
        ]):
            SES.awaiting_confirm = True
            return {
                "success": True,
                "needs_confirm": True,
                "message": "Signup successful! Check your email.",
            }

        if any(k in url_ for k in ["dashboard", "verify", "confirm"]):
            SES.awaiting_confirm = "verify" in url_ or "confirm" in url_
            return {
                "success": True,
                "needs_confirm": SES.awaiting_confirm,
                "message": "Signup submitted!",
            }

        # Check for errors
        error_selectors = [
            ".v-messages__message",
            ".error--text",
            ".v-alert--type-error",
            "[class*='error']",
        ]
        for sel in error_selectors:
            try:
                els = await page.locator(sel).all()
                for el in els:
                    txt = (await el.inner_text()).strip()
                    if txt and len(txt) < 300:
                        return {
                            "success": False,
                            "needs_confirm": False,
                            "message": f"Form error: {txt}",
                        }
            except Exception:
                continue

        # Screenshot for debugging
        await page.screenshot(path="signup_result.png", full_page=True)

        return {
            "success": False,
            "needs_confirm": False,
            "message": (
                "Signup outcome unclear. Possible reasons:\n"
                "• Cloudflare Turnstile not solved\n"
                "• Form validation error\n"
                "• Email already registered\n\n"
                "Check signup_result.png for details."
            ),
        }

    except Exception as exc:
        logger.exception("Signup crashed")
        return {"success": False, "needs_confirm": False, "message": str(exc)}


# ================================================================
#              CORE AUTOMATION — LOGIN
# ================================================================
async def auto_login() -> dict:
    try:
        page = await get_page(headless=True)
        logger.info("🔑 Loading login page...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await human_delay(3.0, 5.0)
        await page.wait_for_load_state("networkidle", timeout=20_000)

        # Email
        logger.info("📧 Filling email...")
        try:
            await page.locator(LOGIN_SELECTORS["email"]).first.click()
            await human_delay()
            await page.keyboard.type(SES.email, delay=80)
            await human_delay(0.5, 1.0)
        except Exception as e:
            return {"success": False, "message": f"Email field: {e}"}

        # Password
        logger.info("🔑 Filling password...")
        try:
            await page.locator(LOGIN_SELECTORS["password"]).first.click()
            await human_delay()
            await page.keyboard.type(SES.password, delay=80)
            await human_delay(0.5, 1.0)
        except Exception as e:
            return {"success": False, "message": f"Password field: {e}"}

        # Cloudflare check
        await human_delay(2.0, 4.0)
        if await page.locator('iframe[src*="challenges.cloudflare.com"]').count() > 0:
            logger.info("🛡️ Turnstile on login - waiting...")
            for i in range(30):
                token = await page.evaluate("""() => {
                    const i = document.querySelector('input[name="cf-turnstile-response"]');
                    return i && i.value && i.value.length > 20 ? i.value : null;
                }""")
                if token:
                    break
                await asyncio.sleep(1)

        # Submit
        logger.info("🚀 Submitting...")
        await page.locator(LOGIN_SELECTORS["submit"]).first.click()
        await human_delay(4.0, 7.0)

        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass

        url_ = page.url.lower()
        logger.info("📍 Post-login URL: %s", url_)

        if any(k in url_ for k in ["dashboard", "publisher", "home", "smartlink"]):
            SES.logged_in = True
            return {"success": True, "message": "Login successful!"}

        # Check errors
        for sel in [".v-messages__message", ".error--text", ".v-alert"]:
            try:
                els = await page.locator(sel).all()
                for el in els:
                    txt = (await el.inner_text()).strip()
                    if txt:
                        return {"success": False, "message": f"Error: {txt}"}
            except Exception:
                continue

        await page.screenshot(path="login_result.png", full_page=True)
        return {"success": False, "message": "Login failed — check login_result.png"}

    except Exception as exc:
        logger.exception("Login crashed")
        return {"success": False, "message": str(exc)}


# ================================================================
#         CORE AUTOMATION — OPEN CONFIRMATION LINK
# ================================================================
async def auto_confirm(url: str) -> dict:
    try:
        page = await get_page(headless=True)
        logger.info("🔗 Opening: %s", url)
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        await human_delay(3.0, 6.0)

        url_  = page.url.lower()
        text_ = (await page.inner_text("body")).lower()

        if any(k in url_ or k in text_ for k in [
            "verified", "confirmed", "success",
            "dashboard", "welcome", "activated",
        ]):
            SES.awaiting_confirm = False
            return {"success": True, "message": "Email confirmed!"}

        if any(k in text_ for k in ["expired", "invalid", "already used"]):
            return {"success": False, "message": "Link expired or invalid."}

        return {"success": True, "message": "Link opened — proceeding to login."}

    except Exception as exc:
        return {"success": False, "message": str(exc)}


# ================================================================
#                  TELEGRAM KEYBOARDS
# ================================================================
def menu(logged_in: bool = False) -> InlineKeyboardMarkup:
    if logged_in:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Status",   callback_data="status")],
            [InlineKeyboardButton("🚪 Logout",   callback_data="logout")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login",                callback_data="login")],
        [InlineKeyboardButton("🎲 Auto Sign Up",         callback_data="auto_signup")],
        [InlineKeyboardButton("✍️ Manual Sign Up",       callback_data="manual_signup")],
        [InlineKeyboardButton("📊 Status",                callback_data="status")],
    ])


CONFIRM_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Use This",     callback_data="confirm_signup"),
        InlineKeyboardButton("🔄 Regenerate",   callback_data="auto_signup"),
    ],
    [InlineKeyboardButton("❌ Cancel",          callback_data="cancel_signup")],
])

LOGOUT_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Yes",          callback_data="logout_yes"),
        InlineKeyboardButton("❌ No",           callback_data="logout_no"),
    ]
])

# ================================================================
#                  TELEGRAM HELPERS
# ================================================================
async def safe_edit(query, text: str, kb=None):
    try:
        await query.edit_message_text(
            text, parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning("edit failed: %s", e)


async def notify(ctx, text: str):
    try:
        await ctx.bot.send_message(
            TELEGRAM_CHAT_ID, text,
            parse_mode="HTML",
        )
    except Exception:
        pass


async def del_msg(update: Update):
    try:
        await update.message.delete()
    except Exception:
        pass


def card(p: Profile) -> str:
    return (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"📧 <b>Email</b>     : <code>{p.email}</code>\n"
        f"👤 <b>Name</b>      : <code>{p.full_name}</code>\n"
        f"🆔 <b>Login</b>     : <code>{p.login}</code>\n"
        f"🔑 <b>Password</b>  : <code>{p.password}</code>\n"
        f"💬 <b>Messenger</b> : {p.messenger}\n"
        f"📱 <b>Account</b>   : <code>{p.messenger_account}</code>\n"
        f"🌍 <b>Country</b>   : {p.country}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>"
    )


# ================================================================
#                  COMMAND HANDLERS
# ================================================================
async def cmd_start(update: Update, ctx):
    user = update.effective_user
    text = (
        f"👋 <b>Hi {user.first_name}!</b>\n\n"
        f"🤖 <b>Adsterra Bot — REAL Edition</b>\n"
        f"<i>Uses actual form selectors from beta site</i>\n\n"
        f"📌 Status: {'🟢 Logged in' if SES.logged_in else '🔴 Not logged in'}\n"
        f"👤 Account: {SES.email or 'N/A'}\n\n"
        f"⚠️ <b>Known Issue:</b>\n"
        f"Adsterra uses <b>Cloudflare Turnstile</b> which blocks\n"
        f"most automated signups. The bot tries its best but\n"
        f"may fail on CAPTCHA. Use a residential proxy or\n"
        f"manual signup if it fails.\n\n"
        f"Choose below:"
    )
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=menu(SES.logged_in),
    )


async def cmd_cancel(update: Update, ctx) -> int:
    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=menu(SES.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#              AUTO SIGNUP CONVERSATION
# ================================================================
async def auto_signup_entry(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()

    if SES.logged_in:
        await safe_edit(q, "✅ Already logged in.", kb=menu(True))
        return ConversationHandler.END

    profile = Generator.make()
    SES.profile = profile

    text = (
        "🎲 <b>Generated Profile</b>\n\n"
        + card(profile)
        + "\n\nReview and confirm:"
    )
    await safe_edit(q, text, kb=CONFIRM_KB)
    return STATE_SIGNUP_CONFIRM


async def signup_confirmed(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()

    p = SES.profile
    if not p:
        await safe_edit(q, "❌ No profile.", kb=menu(False))
        return ConversationHandler.END

    SES.email    = p.email
    SES.password = p.password
    SES.login    = p.login

    await safe_edit(
        q,
        (
            f"⏳ <b>Registering on Adsterra Beta...</b>\n\n"
            + card(p) +
            "\n\n🌐 Browser starting...\n"
            "📝 Filling form...\n"
            "🛡️ Solving CAPTCHA...\n"
            "🚀 Submitting...\n\n"
            "<i>Takes 30–60 seconds</i>"
        ),
    )

    result = await auto_signup(p)

    if result["success"] and result["needs_confirm"]:
        await safe_edit(
            q,
            (
                f"✅ <b>Account Created!</b>\n\n"
                + card(p) +
                f"\n\n📬 <b>Confirmation email sent!</b>\n\n"
                f"<b>Next steps:</b>\n"
                f"1️⃣ Check inbox: <code>{p.email}</code>\n"
                f"2️⃣ Open the confirmation email\n"
                f"3️⃣ <b>Copy the confirmation link</b>\n"
                f"4️⃣ Paste it here in chat\n\n"
                f"<i>Bot will open it and auto-login.</i>"
            ),
        )
        await notify(ctx, f"📝 New Signup\n📧 <code>{p.email}</code>")
        return STATE_CONFIRM_LINK

    elif result["success"]:
        await safe_edit(
            q,
            f"🎉 <b>Signed Up!</b>\n\n📧 <code>{p.email}</code>",
            kb=menu(True),
        )
        return ConversationHandler.END

    else:
        SES.email = SES.password = None
        await safe_edit(
            q,
            f"❌ <b>Signup Failed</b>\n\n⚠️ {result['message']}",
            kb=menu(False),
        )
        return ConversationHandler.END


async def signup_cancel(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()
    SES.profile = None
    await safe_edit(q, "❌ Cancelled.", kb=menu(False))
    return ConversationHandler.END


# ================================================================
#              CONFIRMATION LINK HANDLER
# ================================================================
async def confirm_link(update: Update, ctx) -> int:
    raw  = update.message.text.strip()
    urls = re.findall(r'https?://[^\s]+', raw)
    url  = urls[0] if urls else raw

    if not url.startswith("http"):
        await update.message.reply_text(
            "⚠️ Send a valid URL starting with https://"
        )
        return STATE_CONFIRM_LINK

    msg = await update.message.reply_text(
        f"⏳ Opening confirmation link...\n<code>{url[:60]}</code>",
        parse_mode="HTML",
    )

    result = await auto_confirm(url)

    if result["success"]:
        await msg.edit_text(
            "✅ Confirmed! Auto-logging in...",
            parse_mode="HTML",
        )
        await human_delay(2.0, 4.0)
        await SES._close_browser()

        login = await auto_login()

        if login["success"]:
            await msg.edit_text(
                f"🎉 <b>Account Confirmed & Logged In!</b>\n\n"
                f"📧 <code>{SES.email}</code>",
                parse_mode="HTML",
                reply_markup=menu(True),
            )
            await notify(ctx, f"🎉 Confirmed + Logged In\n📧 <code>{SES.email}</code>")
            return ConversationHandler.END
        else:
            await msg.edit_text(
                "✅ Confirmed but auto-login failed.\n\n"
                "Send your <b>password</b> again:",
                parse_mode="HTML",
            )
            return STATE_RELOGIN_PASSWORD
    else:
        await msg.edit_text(
            f"❌ {result['message']}\n\nSend correct link or /cancel",
        )
        return STATE_CONFIRM_LINK


async def relogin_pw(update: Update, ctx) -> int:
    SES.password = update.message.text.strip()
    await del_msg(update)

    msg = await update.message.reply_text("⏳ Logging in...")
    await SES._close_browser()
    result = await auto_login()

    if result["success"]:
        await msg.edit_text(
            f"✅ Logged in!\n📧 <code>{SES.email}</code>",
            parse_mode="HTML", reply_markup=menu(True),
        )
    else:
        await msg.edit_text(
            f"❌ {result['message']}",
            reply_markup=menu(False),
        )
    return ConversationHandler.END


# ================================================================
#              LOGIN CONVERSATION
# ================================================================
async def login_entry(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()

    if SES.logged_in:
        await safe_edit(q, "✅ Already logged in.", kb=menu(True))
        return ConversationHandler.END

    await safe_edit(q, "📧 Send your Adsterra email:")
    return STATE_LOGIN_EMAIL


async def login_email(update: Update, ctx) -> int:
    email = update.message.text.strip()
    if "@" not in email:
        await update.message.reply_text("⚠️ Invalid email")
        return STATE_LOGIN_EMAIL

    SES.email = email
    await del_msg(update)
    await update.message.reply_text(
        "🔑 Now send your password (deleted instantly):"
    )
    return STATE_LOGIN_PASSWORD


async def login_pw(update: Update, ctx) -> int:
    SES.password = update.message.text.strip()
    await del_msg(update)

    msg = await update.message.reply_text("⏳ Logging in...")
    result = await auto_login()

    if result["success"]:
        await msg.edit_text(
            f"✅ Logged in!\n📧 <code>{SES.email}</code>",
            parse_mode="HTML", reply_markup=menu(True),
        )
        await notify(ctx, f"🟢 Login\n📧 <code>{SES.email}</code>")
    else:
        SES.email = SES.password = None
        await msg.edit_text(
            f"❌ {result['message']}",
            reply_markup=menu(False),
        )
    return ConversationHandler.END


# ================================================================
#              LOGOUT CONVERSATION
# ================================================================
async def logout_entry(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()

    if not SES.email:
        await safe_edit(q, "⚠️ No active session.", kb=menu(False))
        return ConversationHandler.END

    await safe_edit(
        q,
        f"🚪 Logout <code>{SES.email}</code>?",
        kb=LOGOUT_KB,
    )
    return STATE_LOGOUT_CONFIRM


async def logout_yes(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()
    old = SES.email
    await SES.reset()
    await safe_edit(
        q, f"✅ Logged out: <code>{old}</code>",
        kb=menu(False),
    )
    return ConversationHandler.END


async def logout_no(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()
    await safe_edit(q, "✅ Cancelled.", kb=menu(SES.logged_in))
    return ConversationHandler.END


# ================================================================
#              STATUS
# ================================================================
async def show_status(update: Update, ctx) -> int:
    q = update.callback_query
    await q.answer()
    text = (
        f"<b>📊 Status</b>\n"
        f"🔐 Login   : {'🟢' if SES.logged_in else '🔴'}\n"
        f"👤 Account : <code>{SES.email or 'N/A'}</code>\n"
        f"🌐 Browser : {'🟢' if SES.browser_alive else '⚫'}\n"
        f"📧 Confirm : {'⏳' if SES.awaiting_confirm else '✅'}"
    )
    await safe_edit(q, text, kb=menu(SES.logged_in))
    return ConversationHandler.END


# ================================================================
#                          MAIN
# ================================================================
def main():
    logger.info("🚀 Starting Adsterra Bot (REAL Edition)")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Login conv
    login_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(login_entry, pattern="^login$")],
        states={
            STATE_LOGIN_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)],
            STATE_LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_pw)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    # Signup conv
    signup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(auto_signup_entry, pattern="^auto_signup$")],
        states={
            STATE_SIGNUP_CONFIRM: [
                CallbackQueryHandler(signup_confirmed, pattern="^confirm_signup$"),
                CallbackQueryHandler(auto_signup_entry,pattern="^auto_signup$"),
                CallbackQueryHandler(signup_cancel,    pattern="^cancel_signup$"),
            ],
            STATE_CONFIRM_LINK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_link)],
            STATE_RELOGIN_PASSWORD:[MessageHandler(filters.TEXT & ~filters.COMMAND, relogin_pw)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    # Logout conv
    logout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(logout_entry, pattern="^logout$")],
        states={
            STATE_LOGOUT_CONFIRM: [
                CallbackQueryHandler(logout_yes, pattern="^logout_yes$"),
                CallbackQueryHandler(logout_no,  pattern="^logout_no$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(login_conv)
    app.add_handler(signup_conv)
    app.add_handler(logout_conv)
    app.add_handler(CallbackQueryHandler(show_status, pattern="^status$"))

    logger.info("✅ Bot ready! Send /start")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
