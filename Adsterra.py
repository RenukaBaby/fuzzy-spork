#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║     ADSTERRA BETA PUBLISHER BOT - FIXED REAL SELECTORS          ║
║     URL: https://beta.publishers.adsterra.com/signup            ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import random
import logging
import sys
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from playwright.async_api import (
    async_playwright, Page, Browser, BrowserContext, TimeoutError as PWTimeout
)
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
) = range(6)

# ================================================================
#                  REALISTIC TEST DATA
# ================================================================
FIRST_NAMES = [
    "James", "Oliver", "William", "Benjamin", "Lucas",
    "Henry", "Alexander", "Mason", "Ethan", "Daniel",
    "Emma", "Sophia", "Isabella", "Mia", "Charlotte",
    "Amelia", "Harper", "Evelyn", "Abigail", "Emily",
    "Noah", "Liam", "Logan", "Jackson", "Aiden",
    "Sofia", "Avery", "Ella", "Scarlett", "Victoria",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Wilson", "Anderson",
    "Taylor", "Moore", "Jackson", "Martin", "Lee",
    "Thompson", "White", "Harris", "Clark", "Lewis",
    "Walker", "Hall", "Allen", "Young", "King",
    "Wright", "Scott", "Green", "Baker", "Adams",
]

COUNTRIES = [
    "United States", "United Kingdom", "Canada",
    "Australia", "Germany", "France", "Netherlands",
    "Sweden", "Spain", "Italy", "Poland", "Brazil",
]

# ── Messenger options exactly as shown on Adsterra form ──────────
MESSENGERS = ["Telegram", "Skype", "WhatsApp"]

# ── Use REAL email domains so confirmation emails arrive ─────────
REAL_DOMAINS = [
    "gmail.com",
    "outlook.com",
    "yahoo.com",
    "hotmail.com",
    "icloud.com",
    "protonmail.com",
]

PASSWORD_WORDS = [
    "Phoenix", "Storm", "Tiger", "Eagle", "Wolf",
    "Falcon", "Knight", "Dragon", "Blaze", "Cyber",
    "Nova", "Raven", "Alpha", "Omega", "Titan",
]

SPECIALS = ["!", "@", "#", "$", "&"]

# ================================================================
#                  PROFILE DATA CLASS
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

        # Real domain so confirmation email arrives
        email = (
            f"{first.lower()}"
            f".{last.lower()}"
            f"{num}"
            f"@{random.choice(REAL_DOMAINS)}"
        )

        # Login must be alphanumeric, no spaces
        login = f"{first.lower()}{last.lower()}{num}"

        # Strong password
        password = (
            f"{random.choice(PASSWORD_WORDS)}"
            f"{random.randint(10, 99)}"
            f"{random.choice(SPECIALS)}"
            f"{random.choice(PASSWORD_WORDS)}"
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
    email:            Optional[str]           = None
    password:         Optional[str]           = None
    login_name:       Optional[str]           = None
    profile:          Optional[Profile]       = None
    logged_in:        bool                    = False
    awaiting_confirm: bool                    = False
    page:             Optional[Page]          = None
    browser:          Optional[Browser]       = None
    ctx:              Optional[BrowserContext] = None
    _pw:              object                  = None

    def __post_init__(self):
        self._lock = asyncio.Lock()

    @property
    def browser_alive(self) -> bool:
        return self.browser is not None

    async def reset(self):
        async with self._lock:
            self.email            = None
            self.password         = None
            self.login_name       = None
            self.profile          = None
            self.logged_in        = False
            self.awaiting_confirm = False
            await self._close_browser()

    async def _close_browser(self):
        for obj, name in [
            (self.page,    "page"),
            (self.ctx,     "context"),
            (self.browser, "browser"),
        ]:
            if obj:
                try:
                    await obj.close()
                    logger.info("✅ Closed %s", name)
                except Exception as e:
                    logger.warning("Close %s: %s", name, e)

        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass

        self.page = self.ctx = self.browser = self._pw = None


SES = Session()

# ================================================================
#                  STEALTH BROWSER
# ================================================================
STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver',
        { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',
        { get: () => [1,2,3,4,5] });
    Object.defineProperty(navigator, 'languages',
        { get: () => ['en-US','en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency',
        { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory',
        { get: () => 8 });
    window.chrome = {
        runtime: {},
        loadTimes: () => {},
        csi: () => {},
        app: {}
    };
    // Prevent canvas fingerprinting
    const getCtx = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, attrs) {
        const ctx = getCtx.call(this, type, attrs);
        if (type === '2d') {
            const orig = ctx.fillText.bind(ctx);
            ctx.fillText = (...a) => orig(...a);
        }
        return ctx;
    };
"""


async def get_page() -> Page:
    """Get existing page or launch a new stealth browser."""
    if SES.page and not SES.page.is_closed():
        logger.info("♻️  Reusing browser page")
        return SES.page

    logger.info("🌐 Launching stealth browser...")
    SES._pw = await async_playwright().start()

    SES.browser = await SES._pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--window-size=1366,768",
            "--disable-gpu",
            "--disable-infobars",
            "--lang=en-US",
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
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/webp,*/*;q=0.8"
            ),
        },
    )

    await SES.ctx.add_init_script(STEALTH_JS)
    SES.page = await SES.ctx.new_page()
    SES.page.set_default_timeout(60_000)
    logger.info("✅ Browser ready")
    return SES.page


# ================================================================
#                  HUMAN INTERACTION HELPERS
# ================================================================
async def delay(a: float = 0.8, b: float = 2.0):
    await asyncio.sleep(random.uniform(a, b))


async def slow_type(page: Page, text: str):
    """Type text character by character with human-like delays."""
    for ch in text:
        await page.keyboard.type(ch, delay=random.randint(60, 140))
    await delay(0.3, 0.8)


async def fill_input_by_index(page: Page, index: int, text: str, label: str):
    """
    Fill a Vuetify input field by its position index on the page.
    Vuetify wraps inputs in .v-field so we click the wrapper first.
    """
    try:
        # Try clicking the Vuetify field wrapper first
        fields = page.locator(".v-field__input, .v-field input")
        count  = await fields.count()
        logger.info("  Found %d v-field inputs", count)

        if index < count:
            field = fields.nth(index)
            await field.scroll_into_view_if_needed()
            await field.click()
            await delay(0.3, 0.6)
            await slow_type(page, text)
            logger.info("  ✅ %s filled via v-field index %d", label, index)
            return True
    except Exception as e:
        logger.warning("  v-field attempt failed: %s", e)

    try:
        # Fallback: raw input by index
        inputs = page.locator("input")
        count  = await inputs.count()
        if index < count:
            inp = inputs.nth(index)
            await inp.scroll_into_view_if_needed()
            await inp.click()
            await delay(0.3, 0.6)
            # Clear first
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await slow_type(page, text)
            logger.info("  ✅ %s filled via input index %d", label, index)
            return True
    except Exception as e:
        logger.warning("  raw input attempt failed: %s", e)

    logger.error("  ❌ Could not fill %s", label)
    return False


async def fill_input_by_placeholder(page: Page, placeholder: str, text: str):
    """Fill input by its placeholder text (partial match, case-insensitive)."""
    try:
        sel = f'input[placeholder*="{placeholder}" i]'
        el  = page.locator(sel).first
        if await el.count() > 0:
            await el.scroll_into_view_if_needed()
            await el.click()
            await delay(0.2, 0.5)
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await slow_type(page, text)
            logger.info("  ✅ Filled [placeholder~='%s']", placeholder)
            return True
    except Exception as e:
        logger.warning("  placeholder fill failed: %s", e)
    return False


async def select_vuetify_dropdown(
    page: Page,
    dropdown_index: int,
    option_text: str,
    label: str,
):
    """
    Click a Vuetify v-select dropdown (by index) and
    pick the option matching option_text.
    """
    try:
        dropdowns = page.locator(".v-select")
        count     = await dropdowns.count()
        logger.info("  Found %d v-select dropdowns", count)

        if dropdown_index >= count:
            logger.error("  ❌ Dropdown index %d out of range", dropdown_index)
            return False

        dd = dropdowns.nth(dropdown_index)
        await dd.scroll_into_view_if_needed()
        await dd.click()
        await delay(1.0, 2.0)

        logger.info("  Dropdown opened, looking for '%s'...", option_text)

        # Wait for list to appear
        try:
            await page.wait_for_selector(
                ".v-list-item, .v-overlay__content .v-list",
                timeout=5000,
            )
        except Exception:
            pass

        # Try exact text match first
        for sel in [
            f'.v-list-item:has-text("{option_text}")',
            f'.v-list-item__title:has-text("{option_text}")',
            f'[role="option"]:has-text("{option_text}")',
        ]:
            try:
                opt = page.locator(sel).first
                if await opt.count() > 0:
                    await opt.click()
                    logger.info("  ✅ %s selected: %s", label, option_text)
                    await delay(0.5, 1.0)
                    return True
            except Exception:
                continue

        # If not found — type to search
        logger.info("  Typing to search for '%s'...", option_text)
        await page.keyboard.type(option_text[:4], delay=100)
        await delay(1.0, 2.0)

        for sel in [
            f'.v-list-item:has-text("{option_text}")',
            '.v-list-item:first-child',
            '[role="option"]:first-child',
        ]:
            try:
                opt = page.locator(sel).first
                if await opt.count() > 0:
                    await opt.click()
                    logger.info("  ✅ %s selected (search)", label)
                    await delay(0.5, 1.0)
                    return True
            except Exception:
                continue

        # Press Escape to close and continue
        await page.keyboard.press("Escape")
        logger.warning("  ⚠️ %s: option not found", label)
        return False

    except Exception as e:
        logger.error("  ❌ Dropdown %s failed: %s", label, e)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False


# ================================================================
#         TURNSTILE SOLVER (wait + manual fallback)
# ================================================================
async def wait_for_turnstile(page: Page, timeout: int = 25) -> bool:
    """
    Wait for Cloudflare Turnstile to auto-solve.
    Returns True if solved, False if timeout.
    """
    logger.info("🛡️ Checking Turnstile...")

    # Check if Turnstile is present
    try:
        turnstile_frame = page.frame_locator(
            'iframe[src*="challenges.cloudflare.com"]'
        )
        frame_count = await page.locator(
            'iframe[src*="challenges.cloudflare.com"]'
        ).count()
    except Exception:
        frame_count = 0

    if frame_count == 0:
        logger.info("✅ No Turnstile iframe found — continuing")
        return True

    logger.info("⚠️ Turnstile detected! Waiting up to %ds...", timeout)

    for i in range(timeout):
        try:
            # Check if token exists and is non-empty
            token = await page.evaluate("""() => {
                // Check hidden input
                const inputs = document.querySelectorAll(
                    'input[name="cf-turnstile-response"]'
                );
                for (const inp of inputs) {
                    if (inp.value && inp.value.length > 10) return inp.value;
                }

                // Check for success indicator in iframe
                const iframes = document.querySelectorAll('iframe');
                for (const f of iframes) {
                    if (f.src && f.src.includes('challenges.cloudflare')) {
                        // Check if success class is present
                        if (f.classList.contains('passed')) return 'passed';
                        if (f.dataset && f.dataset.passed) return 'passed';
                    }
                }
                return null;
            }""")

            if token:
                logger.info("✅ Turnstile solved! (%ds)", i)
                return True

            # Also check if the widget shows green checkmark
            success = await page.evaluate("""() => {
                const widget = document.querySelector(
                    '.cf-turnstile [data-action], '
                    '.cf-turnstile-wrapper'
                );
                if (widget) {
                    const style = window.getComputedStyle(widget);
                    return widget.innerHTML.includes('success') ||
                           widget.dataset.solved === 'true';
                }
                return false;
            }""")

            if success:
                logger.info("✅ Turnstile widget shows success")
                return True

        except Exception:
            pass

        await asyncio.sleep(1)

    logger.warning("⏰ Turnstile timeout after %ds", timeout)
    return False


# ================================================================
#              CORE AUTOMATION — SIGN UP (FIXED)
# ================================================================
async def auto_signup(profile: Profile) -> dict:
    """
    Fixed Adsterra Beta signup using correct field positions.

    Form layout (from screenshot):
    Row 1: [E-mail]           [First and Last Name]
    Row 2: [Login]            [Password]
    Row 3: [Messenger▼]       [Messenger account]
    Row 4: [Select country▼]
    Row 5: [Cloudflare Turnstile ✅]
    Row 6: [☐ Terms checkbox]
    Row 7: [SIGN UP button]
    """
    try:
        # Fresh browser for each signup attempt
        await SES._close_browser()
        page = await get_page()

        logger.info("=" * 50)
        logger.info("📝 Starting signup for: %s", profile.email)
        logger.info("=" * 50)

        # ── Navigate ──────────────────────────────────────────
        logger.info("🌐 Loading signup page...")
        await page.goto(SIGNUP_URL, wait_until="domcontentloaded")

        # Wait for Vue app to fully mount
        try:
            await page.wait_for_selector(".v-field, input", timeout=15_000)
        except Exception:
            pass
        await delay(3.0, 5.0)

        # Screenshot before filling
        await page.screenshot(path="debug_before_fill.png", full_page=True)
        logger.info("📸 debug_before_fill.png saved")

        # ── Dump all inputs for debugging ─────────────────────
        all_inputs = await page.evaluate("""() => {
            const inputs = document.querySelectorAll('input');
            return Array.from(inputs).map((inp, i) => ({
                index: i,
                type: inp.type,
                placeholder: inp.placeholder,
                name: inp.name,
                id: inp.id,
                autocomplete: inp.autocomplete,
                ariaLabel: inp.getAttribute('aria-label'),
                class: inp.className.substring(0, 50),
            }));
        }""")
        logger.info("🔍 Found %d inputs:", len(all_inputs))
        for inp in all_inputs:
            logger.info("  %s", inp)

        # ── Dump all v-selects ────────────────────────────────
        selects = await page.evaluate("""() => {
            const sels = document.querySelectorAll('.v-select');
            return Array.from(sels).map((s, i) => ({
                index: i,
                label: s.querySelector('label') ?
                       s.querySelector('label').textContent.trim() : '',
                class: s.className.substring(0, 80),
            }));
        }""")
        logger.info("🔍 Found %d v-selects:", len(selects))
        for s in selects:
            logger.info("  %s", s)

        # ── STEP 1: E-mail ────────────────────────────────────
        logger.info("\n── Step 1: Email ──")
        filled = await fill_input_by_placeholder(page, "E-mail", profile.email)
        if not filled:
            filled = await fill_input_by_placeholder(page, "mail", profile.email)
        if not filled:
            filled = await fill_input_by_index(page, 0, profile.email, "Email")
        await delay(0.5, 1.0)

        # ── STEP 2: First and Last Name ───────────────────────
        logger.info("\n── Step 2: Full Name ──")
        filled = await fill_input_by_placeholder(
            page, "First and Last Name", profile.full_name
        )
        if not filled:
            filled = await fill_input_by_placeholder(page, "Name", profile.full_name)
        if not filled:
            filled = await fill_input_by_index(page, 1, profile.full_name, "FullName")
        await delay(0.5, 1.0)

        # ── STEP 3: Login ─────────────────────────────────────
        logger.info("\n── Step 3: Login ──")
        filled = await fill_input_by_placeholder(page, "Login", profile.login)
        if not filled:
            filled = await fill_input_by_index(page, 2, profile.login, "Login")
        await delay(0.5, 1.0)

        # ── STEP 4: Password ──────────────────────────────────
        logger.info("\n── Step 4: Password ──")
        try:
            pw = page.locator('input[type="password"]').first
            if await pw.count() > 0:
                await pw.scroll_into_view_if_needed()
                await pw.click()
                await delay(0.2, 0.5)
                await slow_type(page, profile.password)
                logger.info("  ✅ Password filled")
            else:
                await fill_input_by_placeholder(page, "Password", profile.password)
        except Exception as e:
            logger.error("  Password failed: %s", e)
        await delay(0.5, 1.0)

        # ── STEP 5: Messenger Dropdown ────────────────────────
        logger.info("\n── Step 5: Messenger dropdown ──")
        await select_vuetify_dropdown(
            page, 0, profile.messenger, "Messenger"
        )
        await delay(0.5, 1.0)

        # ── STEP 6: Messenger Account ─────────────────────────
        logger.info("\n── Step 6: Messenger account ──")
        filled = await fill_input_by_placeholder(
            page, "Messenger account", profile.messenger_account
        )
        if not filled:
            filled = await fill_input_by_placeholder(
                page, "account", profile.messenger_account
            )
        if not filled:
            # After messenger dropdown selection,
            # account input appears — try index 4
            filled = await fill_input_by_index(
                page, 4, profile.messenger_account, "MessengerAccount"
            )
        await delay(0.5, 1.0)

        # ── STEP 7: Country Dropdown ──────────────────────────
        logger.info("\n── Step 7: Country dropdown ──")
        await select_vuetify_dropdown(
            page, 1, profile.country, "Country"
        )
        await delay(1.0, 2.0)

        # Screenshot after filling all fields
        await page.screenshot(path="debug_after_fill.png", full_page=True)
        logger.info("📸 debug_after_fill.png saved")

        # ── STEP 8: Wait for Turnstile ────────────────────────
        logger.info("\n── Step 8: Cloudflare Turnstile ──")
        turnstile_ok = await wait_for_turnstile(page, timeout=30)

        if not turnstile_ok:
            return {
                "success":       False,
                "needs_confirm": False,
                "message": (
                    "🛡️ <b>Cloudflare Turnstile blocked signup</b>\n\n"
                    "The CAPTCHA did not solve automatically.\n\n"
                    "This happens because:\n"
                    "• GitHub Actions IP is flagged as datacenter\n"
                    "• Headless browser detected\n\n"
                    "<b>Solutions:</b>\n"
                    "• The bot will retry automatically\n"
                    "• Try again in a few minutes\n"
                    "• Sometimes it works on retry!"
                ),
            }

        # ── STEP 9: Terms & Conditions Checkbox ───────────────
        logger.info("\n── Step 9: Terms checkbox ──")
        try:
            # Vuetify checkbox — click the label/wrapper not input
            checkbox_wrappers = [
                ".v-checkbox",
                ".v-selection-control",
                'label:has(input[type="checkbox"])',
                ".v-checkbox-btn",
            ]
            checked = False
            for sel in checkbox_wrappers:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.scroll_into_view_if_needed()
                        await el.click()
                        await delay(0.5, 1.0)

                        # Verify it's checked
                        cb = page.locator('input[type="checkbox"]').first
                        if await cb.count() > 0:
                            is_checked = await cb.is_checked()
                            if is_checked:
                                logger.info("  ✅ Terms checked via: %s", sel)
                                checked = True
                                break
                except Exception:
                    continue

            if not checked:
                # Direct click on checkbox input
                cb = page.locator('input[type="checkbox"]').first
                if await cb.count() > 0:
                    await cb.evaluate("el => el.click()")
                    logger.info("  ✅ Terms checked via JS click")

        except Exception as e:
            logger.error("  Terms checkbox error: %s", e)

        await delay(1.0, 2.0)

        # Screenshot before submit
        await page.screenshot(path="debug_before_submit.png", full_page=True)
        logger.info("📸 debug_before_submit.png saved")

        # ── STEP 10: Click SIGN UP ────────────────────────────
        logger.info("\n── Step 10: Submit SIGN UP ──")
        submitted = False

        submit_selectors = [
            'button:has-text("SIGN UP")',
            'button:has-text("Sign up")',
            'button:has-text("Sign Up")',
            'button[type="submit"]',
            '.v-btn:has-text("SIGN UP")',
            '.v-btn:has-text("sign")',
        ]

        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    logger.info("  ✅ Submitted via: %s", sel)
                    submitted = True
                    break
            except Exception as e:
                logger.warning("  Submit attempt failed [%s]: %s", sel, e)
                continue

        if not submitted:
            # JS click fallback
            try:
                await page.evaluate("""() => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.textContent.trim().toUpperCase()
                                .includes('SIGN')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                logger.info("  ✅ Submitted via JS fallback")
                submitted = True
            except Exception as e:
                return {
                    "success":       False,
                    "needs_confirm": False,
                    "message":       f"Submit button not found: {e}",
                }

        # ── STEP 11: Detect outcome ───────────────────────────
        logger.info("\n── Step 11: Waiting for response ──")
        await delay(5.0, 8.0)

        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        await page.screenshot(path="debug_after_submit.png", full_page=True)
        logger.info("📸 debug_after_submit.png saved")

        url_now   = page.url.lower()
        body_text = ""
        try:
            body_text = (await page.inner_text("body")).lower()
        except Exception:
            pass

        logger.info("📍 Post-submit URL: %s", url_now)
        logger.info("📄 Body snippet: %s...", body_text[:200])

        # ── Success: email confirmation needed ────────────────
        confirm_keywords = [
            "confirm your email",
            "verify your email",
            "check your email",
            "confirmation email",
            "sent to your email",
            "activate your account",
            "verification link",
            "please check",
        ]
        if any(k in body_text for k in confirm_keywords):
            SES.awaiting_confirm = True
            logger.info("✅ SIGNUP SUCCESS — confirmation email sent")
            return {
                "success":       True,
                "needs_confirm": True,
                "message":       "Signup done! Confirmation email sent.",
            }

        # ── Success: direct dashboard redirect ────────────────
        if any(k in url_now for k in ["dashboard", "home", "publisher"]):
            SES.logged_in = True
            logger.info("✅ SIGNUP SUCCESS — logged in directly")
            return {
                "success":       True,
                "needs_confirm": False,
                "message":       "Signup done! Logged in.",
            }

        # ── Success: went to verify/confirm page ─────────────
        if any(k in url_now for k in ["verify", "confirm", "success"]):
            SES.awaiting_confirm = True
            logger.info("✅ SIGNUP — redirected to confirm page")
            return {
                "success":       True,
                "needs_confirm": True,
                "message":       "Signup done! Check your email.",
            }

        # ── Detect form validation errors ─────────────────────
        error_selectors = [
            ".v-messages__message",
            ".v-messages",
            ".error--text",
            ".v-input--error .v-messages__message",
            ".v-alert",
            '[class*="error"]',
        ]
        errors_found = []
        for sel in error_selectors:
            try:
                els = await page.locator(sel).all()
                for el in els:
                    txt = (await el.inner_text()).strip()
                    if txt and len(txt) < 200 and txt not in errors_found:
                        errors_found.append(txt)
            except Exception:
                continue

        if errors_found:
            err_text = "\n".join(f"• {e}" for e in errors_found[:5])
            logger.error("❌ Form errors: %s", errors_found)
            return {
                "success":       False,
                "needs_confirm": False,
                "message":       f"Form validation errors:\n{err_text}",
            }

        # ── Unknown outcome ───────────────────────────────────
        logger.warning("⚠️ Signup outcome unclear")
        return {
            "success":       False,
            "needs_confirm": False,
            "message": (
                "Signup outcome unclear.\n\n"
                "Possible causes:\n"
                "• Turnstile not solved\n"
                "• Email already registered\n"
                "• Form field not filled correctly\n\n"
                "Check debug screenshots in artifacts."
            ),
        }

    except Exception as exc:
        logger.exception("💥 Signup crashed")
        try:
            await page.screenshot(path="debug_crash.png", full_page=True)
        except Exception:
            pass
        return {
            "success":       False,
            "needs_confirm": False,
            "message":       f"Crash: {exc}",
        }


# ================================================================
#              CORE AUTOMATION — LOGIN (FIXED)
# ================================================================
async def auto_login() -> dict:
    """
    Login page layout:
    [E-mail / Login input]
    [Password input]
    [Cloudflare Turnstile]
    [LOG IN button]
    """
    try:
        # Always fresh browser for login
        await SES._close_browser()
        page = await get_page()

        logger.info("🔑 Loading login page: %s", LOGIN_URL)
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector(".v-field, input", timeout=15_000)
        except Exception:
            pass
        await delay(3.0, 5.0)

        await page.screenshot(path="debug_login_before.png", full_page=True)

        # Dump inputs
        all_inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(
                (inp, i) => ({
                    index: i,
                    type: inp.type,
                    placeholder: inp.placeholder,
                    name: inp.name,
                    autocomplete: inp.autocomplete,
                })
            );
        }""")
        logger.info("🔍 Login inputs: %s", all_inputs)

        # ── Email / Login ─────────────────────────────────────
        logger.info("📧 Filling email...")
        filled = await fill_input_by_placeholder(page, "E-mail", SES.email)
        if not filled:
            filled = await fill_input_by_placeholder(page, "Login", SES.email)
        if not filled:
            filled = await fill_input_by_placeholder(page, "mail", SES.email)
        if not filled:
            # Try type="email" input
            try:
                el = page.locator('input[type="email"]').first
                if await el.count() > 0:
                    await el.click()
                    await slow_type(page, SES.email)
                    filled = True
            except Exception:
                pass
        if not filled:
            await fill_input_by_index(page, 0, SES.email, "Email")
        await delay(0.5, 1.0)

        # ── Password ──────────────────────────────────────────
        logger.info("🔑 Filling password...")
        try:
            pw = page.locator('input[type="password"]').first
            if await pw.count() > 0:
                await pw.click()
                await delay(0.2, 0.5)
                await slow_type(page, SES.password)
                logger.info("  ✅ Password filled")
            else:
                await fill_input_by_placeholder(page, "Password", SES.password)
        except Exception as e:
            logger.error("  Password error: %s", e)
        await delay(0.5, 1.0)

        # ── Turnstile ─────────────────────────────────────────
        logger.info("🛡️ Checking Turnstile on login...")
        await wait_for_turnstile(page, timeout=25)

        # ── Submit ────────────────────────────────────────────
        logger.info("🚀 Clicking LOG IN...")
        await page.screenshot(path="debug_login_filled.png", full_page=True)

        login_btn_selectors = [
            'button:has-text("LOG IN")',
            'button:has-text("Log in")',
            'button:has-text("Log In")',
            'button:has-text("Login")',
            'button[type="submit"]',
            '.v-btn:has-text("LOG")',
        ]

        clicked = False
        for sel in login_btn_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click()
                    logger.info("  ✅ Clicked: %s", sel)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            await page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.toUpperCase().includes('LOG')) {
                        btn.click(); return;
                    }
                }
            }""")

        await delay(5.0, 8.0)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        await page.screenshot(path="debug_login_after.png", full_page=True)
        url_now = page.url.lower()
        logger.info("📍 Post-login URL: %s", url_now)

        # ── Check success ─────────────────────────────────────
        if any(k in url_now for k in [
            "dashboard", "publisher", "home",
            "smartlink", "site", "statistics",
        ]):
            SES.logged_in = True
            logger.info("✅ LOGIN SUCCESS")
            return {"success": True, "message": "Login successful!"}

        # Check page text
        try:
            body = (await page.inner_text("body")).lower()
            if any(k in body for k in ["dashboard", "smartlink", "logout", "sign out"]):
                SES.logged_in = True
                return {"success": True, "message": "Login successful!"}
        except Exception:
            pass

        # ── Check errors ──────────────────────────────────────
        errors = []
        for sel in [".v-messages__message", ".v-alert", ".error--text"]:
            try:
                els = await page.locator(sel).all()
                for el in els:
                    t = (await el.inner_text()).strip()
                    if t and t not in errors:
                        errors.append(t)
            except Exception:
                continue

        if errors:
            return {"success": False, "message": "\n".join(errors[:3])}

        return {
            "success": False,
            "message": "Login failed — wrong credentials or CAPTCHA blocked.",
        }

    except Exception as exc:
        logger.exception("💥 Login crashed")
        return {"success": False, "message": f"Crash: {exc}"}


# ================================================================
#         CORE AUTOMATION — EMAIL CONFIRMATION LINK
# ================================================================
async def auto_confirm(confirm_url: str) -> dict:
    try:
        page = await get_page()
        logger.info("🔗 Opening: %s", confirm_url)
        await page.goto(confirm_url, wait_until="networkidle", timeout=30_000)
        await delay(3.0, 6.0)

        await page.screenshot(path="debug_confirm.png", full_page=True)

        url_now   = page.url.lower()
        body_text = (await page.inner_text("body")).lower()

        logger.info("📍 Confirm URL: %s", url_now)

        if any(k in url_now or k in body_text for k in [
            "verified", "confirmed", "success",
            "dashboard", "welcome", "activated",
            "email confirmed", "account confirmed",
        ]):
            SES.awaiting_confirm = False
            return {"success": True, "message": "Email confirmed!"}

        if any(k in body_text for k in [
            "expired", "invalid", "already used",
            "link is no longer", "token",
        ]):
            return {
                "success": False,
                "message": "Link expired or invalid. Request a new one.",
            }

        return {
            "success": True,
            "message": "Link opened — attempting login now.",
        }

    except Exception as exc:
        return {"success": False, "message": f"Error: {exc}"}


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
        [InlineKeyboardButton("🔐 Login",          callback_data="login")],
        [InlineKeyboardButton("🎲 Auto Sign Up",   callback_data="auto_signup")],
        [InlineKeyboardButton("📊 Status",         callback_data="status")],
    ])


CONFIRM_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Confirm & Register", callback_data="confirm_signup"),
        InlineKeyboardButton("🔄 New Profile",        callback_data="auto_signup"),
    ],
    [InlineKeyboardButton("❌ Cancel",                callback_data="cancel_signup")],
])

LOGOUT_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Yes, Logout", callback_data="logout_yes"),
        InlineKeyboardButton("❌ No",          callback_data="logout_no"),
    ]
])


# ================================================================
#                  TELEGRAM HELPERS
# ================================================================
async def safe_edit(query, text: str, kb=None):
    try:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning("safe_edit: %s", e)


async def notify(ctx, text: str):
    try:
        await ctx.bot.send_message(
            TELEGRAM_CHAT_ID, text, parse_mode="HTML"
        )
    except Exception:
        pass


async def del_msg(update: Update):
    try:
        await update.message.delete()
    except Exception:
        pass


def profile_card(p: Profile) -> str:
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
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 <b>Hi {user.first_name}!</b>\n\n"
        f"🤖 <b>Adsterra Beta Publisher Bot</b>\n"
        f"<code>beta.publishers.adsterra.com</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"📌 Status  : {'🟢 Logged in' if SES.logged_in else '🔴 Not logged in'}\n"
        f"👤 Account : <code>{SES.email or 'N/A'}</code>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"Choose below 👇"
    )
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=menu(SES.logged_in),
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ Cancelled.", reply_markup=menu(SES.logged_in)
    )
    return ConversationHandler.END


# ================================================================
#              AUTO SIGNUP CONVERSATION
# ================================================================
async def auto_signup_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    if SES.logged_in:
        await safe_edit(q, "✅ Already logged in.", kb=menu(True))
        return ConversationHandler.END

    # Generate fresh profile
    profile     = Generator.make()
    SES.profile = profile

    text = (
        "🎲 <b>Generated Adsterra Profile</b>\n\n"
        + profile_card(profile)
        + "\n\n<i>Review and confirm to register:</i>"
    )
    await safe_edit(q, text, kb=CONFIRM_KB)
    return STATE_SIGNUP_CONFIRM


async def signup_confirmed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    p = SES.profile
    if not p:
        await safe_edit(q, "❌ No profile found.", kb=menu(False))
        return ConversationHandler.END

    SES.email       = p.email
    SES.password    = p.password
    SES.login_name  = p.login

    await safe_edit(
        q,
        (
            f"⏳ <b>Registering on Adsterra Beta...</b>\n\n"
            + profile_card(p) +
            "\n\n<b>Progress:</b>\n"
            "🌐 Launching browser...\n"
            "📝 Filling all form fields...\n"
            "🛡️ Waiting for Cloudflare...\n"
            "🚀 Submitting form...\n\n"
            "<i>⏳ Please wait 30–90 seconds...</i>"
        ),
    )

    result = await auto_signup(p)

    # ── Success + email confirmation ──────────────────────────
    if result["success"] and result.get("needs_confirm"):
        await safe_edit(
            q,
            (
                f"✅ <b>Account Created!</b>\n\n"
                + profile_card(p) +
                f"\n\n📬 <b>Confirmation email sent to:</b>\n"
                f"<code>{p.email}</code>\n\n"
                f"<b>📋 Next Steps:</b>\n"
                f"1️⃣ Open your email inbox\n"
                f"2️⃣ Find email from Adsterra\n"
                f"3️⃣ Click the confirmation link\n"
                f"4️⃣ <b>Copy the full link URL</b>\n"
                f"5️⃣ Paste it here in this chat\n\n"
                f"<i>Bot will open it automatically and log you in!</i>"
            ),
        )
        await notify(
            ctx,
            f"📝 <b>New Signup!</b>\n"
            f"📧 <code>{p.email}</code>\n"
            f"🔑 <code>{p.password}</code>\n"
            f"⏳ Awaiting email confirmation",
        )
        return STATE_CONFIRM_LINK

    # ── Success + direct login ────────────────────────────────
    elif result["success"]:
        await safe_edit(
            q,
            f"🎉 <b>Registered & Logged In!</b>\n\n"
            f"📧 <code>{p.email}</code>",
            kb=menu(True),
        )
        return ConversationHandler.END

    # ── Failed ────────────────────────────────────────────────
    else:
        SES.email = SES.password = None
        await safe_edit(
            q,
            f"❌ <b>Signup Failed</b>\n\n"
            f"⚠️ {result['message']}\n\n"
            f"<i>Tap 🔄 to try again with a new profile.</i>",
            kb=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data="auto_signup")],
                [InlineKeyboardButton("🏠 Menu",      callback_data="main_menu")],
            ]),
        )
        return ConversationHandler.END


async def signup_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    SES.profile = None
    await safe_edit(q, "❌ Signup cancelled.", kb=menu(False))
    return ConversationHandler.END


# ================================================================
#              CONFIRMATION LINK HANDLER
# ================================================================
async def confirm_link_handler(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    raw  = update.message.text.strip()
    urls = re.findall(r'https?://[^\s<>"]+', raw)
    url  = urls[0] if urls else raw

    if not url.startswith("http"):
        await update.message.reply_text(
            "⚠️ <b>Invalid URL</b>\n\n"
            "Please paste the full confirmation link\n"
            "from your email (starts with <code>https://</code>)",
            parse_mode="HTML",
        )
        return STATE_CONFIRM_LINK

    msg = await update.message.reply_text(
        f"⏳ <b>Opening confirmation link...</b>\n\n"
        f"<code>{url[:70]}{'...' if len(url)>70 else ''}</code>",
        parse_mode="HTML",
    )

    result = await auto_confirm(url)

    if result["success"]:
        await msg.edit_text(
            "✅ <b>Link opened! Auto-logging in...</b>\n\n"
            "<i>15–20 seconds...</i>",
            parse_mode="HTML",
        )

        await delay(2.0, 3.0)
        await SES._close_browser()
        login_result = await auto_login()

        if login_result["success"]:
            p = SES.profile
            await msg.edit_text(
                f"🎉 <b>Account Confirmed & Logged In!</b>\n\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"📧 <code>{SES.email}</code>\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                f"✅ Your account is fully active!",
                parse_mode="HTML",
                reply_markup=menu(True),
            )
            await notify(
                ctx,
                f"🎉 <b>Confirmed + Logged In!</b>\n"
                f"📧 <code>{SES.email}</code>",
            )
            return ConversationHandler.END

        else:
            await msg.edit_text(
                "✅ <b>Email Confirmed!</b>\n\n"
                "⚠️ Auto-login failed.\n\n"
                "🔑 <b>Please send your password again:</b>\n"
                "<i>(deleted immediately for security)</i>",
                parse_mode="HTML",
            )
            return STATE_RELOGIN_PASSWORD

    else:
        await msg.edit_text(
            f"❌ <b>Confirmation Failed</b>\n\n"
            f"⚠️ {result['message']}\n\n"
            f"Please send the correct link or /cancel",
            parse_mode="HTML",
        )
        return STATE_CONFIRM_LINK


async def relogin_password(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    SES.password = update.message.text.strip()
    await del_msg(update)

    msg = await update.message.reply_text("⏳ Logging in...")
    await SES._close_browser()
    result = await auto_login()

    if result["success"]:
        await msg.edit_text(
            f"✅ <b>Logged In!</b>\n📧 <code>{SES.email}</code>",
            parse_mode="HTML",
            reply_markup=menu(True),
        )
    else:
        await msg.edit_text(
            f"❌ <b>Login Failed</b>\n\n{result['message']}",
            reply_markup=menu(False),
        )
    return ConversationHandler.END


# ================================================================
#              LOGIN CONVERSATION
# ================================================================
async def login_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    if SES.logged_in:
        await safe_edit(q, "✅ Already logged in.", kb=menu(True))
        return ConversationHandler.END

    await safe_edit(
        q,
        "🔐 <b>Login to Adsterra</b>\n\n"
        "📧 Send your <b>email address</b>:",
    )
    return STATE_LOGIN_EMAIL


async def login_email_handler(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("⚠️ Invalid email. Try again:")
        return STATE_LOGIN_EMAIL

    SES.email = email
    await del_msg(update)
    await update.message.reply_text(
        "🔑 Send your <b>password</b>:\n"
        "<i>Deleted instantly for security.</i>",
        parse_mode="HTML",
    )
    return STATE_LOGIN_PASSWORD


async def login_password_handler(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    SES.password = update.message.text.strip()
    await del_msg(update)

    msg = await update.message.reply_text(
        "⏳ <b>Logging in...</b>\n\n"
        "🌐 Loading login page...\n"
        "📧 Filling credentials...\n"
        "🛡️ Handling CAPTCHA...\n\n"
        "<i>30–60 seconds...</i>",
        parse_mode="HTML",
    )
    result = await auto_login()

    if result["success"]:
        await msg.edit_text(
            f"✅ <b>Logged In!</b>\n\n"
            f"📧 <code>{SES.email}</code>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="HTML",
            reply_markup=menu(True),
        )
        await notify(ctx, f"🟢 Login\n📧 <code>{SES.email}</code>")
    else:
        SES.email = SES.password = None
        await msg.edit_text(
            f"❌ <b>Login Failed</b>\n\n{result['message']}",
            reply_markup=menu(False),
        )
    return ConversationHandler.END


# ================================================================
#              LOGOUT CONVERSATION
# ================================================================
async def logout_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    if not SES.email:
        await safe_edit(q, "⚠️ No active session.", kb=menu(False))
        return ConversationHandler.END

    await safe_edit(
        q,
        f"🚪 <b>Logout</b> <code>{SES.email}</code>?\n\n"
        f"This will close all browser sessions.",
        kb=LOGOUT_KB,
    )
    return STATE_LOGOUT_CONFIRM


async def logout_yes_handler(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    q = update.callback_query
    await q.answer()
    old = SES.email
    await SES.reset()
    await safe_edit(
        q,
        f"✅ <b>Logged Out</b>\n📧 <code>{old}</code>",
        kb=menu(False),
    )
    return ConversationHandler.END


async def logout_no_handler(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    q = update.callback_query
    await q.answer()
    await safe_edit(q, "✅ Cancelled.", kb=menu(SES.logged_in))
    return ConversationHandler.END


# ================================================================
#              STATUS
# ================================================================
async def show_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    text = (
        f"<b>📊 Bot Status</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔐 Login   : {'🟢 Active' if SES.logged_in else '🔴 None'}\n"
        f"👤 Account : <code>{SES.email or 'N/A'}</code>\n"
        f"🌐 Browser : {'🟢 Running' if SES.browser_alive else '⚫ Off'}\n"
        f"📧 Confirm : {'⏳ Pending' if SES.awaiting_confirm else '✅ OK'}\n"
        f"🕐 Time    : {datetime.now().strftime('%H:%M:%S')}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await safe_edit(q, text, kb=menu(SES.logged_in))
    return ConversationHandler.END


async def main_menu_handler(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    q = update.callback_query
    await q.answer()
    await safe_edit(
        q, "🏠 <b>Main Menu</b>", kb=menu(SES.logged_in)
    )
    return ConversationHandler.END


# ================================================================
#              ERROR HANDLER
# ================================================================
async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled: %s", ctx.error, exc_info=ctx.error)


# ================================================================
#                          MAIN
# ================================================================
def main():
    logger.info("=" * 55)
    logger.info("  ADSTERRA BETA BOT — Fixed Real Selectors")
    logger.info("  URL: %s", SIGNUP_URL)
    logger.info("=" * 55)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Login Conversation ────────────────────────────────────
    login_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(login_entry, pattern="^login$")
        ],
        states={
            STATE_LOGIN_EMAIL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    login_email_handler,
                )
            ],
            STATE_LOGIN_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    login_password_handler,
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    # ── Signup Conversation ───────────────────────────────────
    signup_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(auto_signup_entry, pattern="^auto_signup$")
        ],
        states={
            STATE_SIGNUP_CONFIRM: [
                CallbackQueryHandler(
                    signup_confirmed, pattern="^confirm_signup$"
                ),
                CallbackQueryHandler(
                    auto_signup_entry, pattern="^auto_signup$"
                ),
                CallbackQueryHandler(
                    signup_cancel, pattern="^cancel_signup$"
                ),
            ],
            STATE_CONFIRM_LINK: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    confirm_link_handler,
                )
            ],
            STATE_RELOGIN_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    relogin_password,
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    # ── Logout Conversation ───────────────────────────────────
    logout_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(logout_entry, pattern="^logout$")
        ],
        states={
            STATE_LOGOUT_CONFIRM: [
                CallbackQueryHandler(
                    logout_yes_handler, pattern="^logout_yes$"
                ),
                CallbackQueryHandler(
                    logout_no_handler, pattern="^logout_no$"
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    # ── Register All ──────────────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(login_conv)
    app.add_handler(signup_conv)
    app.add_handler(logout_conv)
    app.add_handler(
        CallbackQueryHandler(show_status,      pattern="^status$")
    )
    app.add_handler(
        CallbackQueryHandler(main_menu_handler, pattern="^main_menu$")
    )
    app.add_error_handler(error_handler)

    logger.info("✅ Bot running! Send /start in Telegram.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
