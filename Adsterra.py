#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║        ADSTERRA AUTOMATION BOT - GOD LEVEL EDITION              ║
║     Realistic Test Data Generator + Full Signup Automation       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import random
import logging
import sys
import re
import string
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

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
ADSTERRA_SIGNUP_URL:    str = "https://publishers.adsterra.com/register"
ADSTERRA_SMARTLINK_URL: str = "https://publishers.adsterra.com/smartlink"
ADSTERRA_DASHBOARD_URL: str = "https://publishers.adsterra.com/dashboard"

# ================================================================
#                   CONVERSATION STATES
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
    STATE_MANUAL_PASSWORD,
    STATE_MANUAL_WEBSITE,
    STATE_MANUAL_COUNTRY,
    STATE_MANUAL_TELEGRAM,
) = range(12)

# ================================================================
#                  REALISTIC TEST DATA BANK
# ================================================================

# ── First Names ───────────────────────────────────────────────
FIRST_NAMES = [
    "James", "Oliver", "William", "Benjamin", "Lucas",
    "Henry", "Alexander", "Mason", "Ethan", "Daniel",
    "Matthew", "Aiden", "Logan", "Jackson", "Sebastian",
    "Emma", "Sophia", "Isabella", "Mia", "Charlotte",
    "Amelia", "Harper", "Evelyn", "Abigail", "Emily",
    "Elizabeth", "Sofia", "Avery", "Ella", "Scarlett",
    "Liam", "Noah", "Owen", "Carter", "Wyatt",
    "Julian", "Grayson", "Levi", "Isaac", "Lincoln",
    "Hannah", "Lillian", "Addison", "Aubrey", "Ellie",
    "Stella", "Natalie", "Zoe", "Leah", "Hazel",
    "Ryan", "Nathan", "Aaron", "Charles", "Thomas",
    "Christopher", "Andrew", "Joshua", "David", "Joseph",
]

# ── Last Names ────────────────────────────────────────────────
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris",
    "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright",
    "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall",
    "Rivera", "Campbell", "Mitchell", "Carter", "Roberts",
]

# ── Countries with realistic publisher data ───────────────────
COUNTRIES = [
    # Tier 1
    {"name": "United States", "code": "US", "tld": "com", "tier": 1},
    {"name": "United Kingdom", "code": "GB", "tld": "co.uk", "tier": 1},
    {"name": "Canada",         "code": "CA", "tld": "ca",    "tier": 1},
    {"name": "Australia",      "code": "AU", "tld": "com.au","tier": 1},
    {"name": "Germany",        "code": "DE", "tld": "de",    "tier": 1},
    {"name": "France",         "code": "FR", "tld": "fr",    "tier": 1},
    {"name": "Netherlands",    "code": "NL", "tld": "nl",    "tier": 1},
    {"name": "Sweden",         "code": "SE", "tld": "se",    "tier": 1},
    # Tier 2
    {"name": "Brazil",         "code": "BR", "tld": "com.br","tier": 2},
    {"name": "Mexico",         "code": "MX", "tld": "com.mx","tier": 2},
    {"name": "Spain",          "code": "ES", "tld": "es",    "tier": 2},
    {"name": "Italy",          "code": "IT", "tld": "it",    "tier": 2},
    {"name": "Poland",         "code": "PL", "tld": "pl",    "tier": 2},
    {"name": "Turkey",         "code": "TR", "tld": "com.tr","tier": 2},
    {"name": "Argentina",      "code": "AR", "tld": "com.ar","tier": 2},
    # Tier 3
    {"name": "India",          "code": "IN", "tld": "in",    "tier": 3},
    {"name": "Indonesia",      "code": "ID", "tld": "co.id", "tier": 3},
    {"name": "Nigeria",        "code": "NG", "tld": "com.ng","tier": 3},
    {"name": "Pakistan",       "code": "PK", "tld": "pk",    "tier": 3},
    {"name": "Bangladesh",     "code": "BD", "tld": "com.bd","tier": 3},
]

# ── Website niches ────────────────────────────────────────────
WEBSITE_NICHES = [
    # Entertainment
    {"niche": "entertainment", "keywords": ["fun",    "viral",  "buzz",   "trend",  "daily"]},
    {"niche": "news",          "keywords": ["news",   "today",  "global", "world",  "info"]},
    {"niche": "tech",          "keywords": ["tech",   "digital","cyber",  "geek",   "byte"]},
    {"niche": "gaming",        "keywords": ["game",   "play",   "gamer",  "quest",  "pixel"]},
    {"niche": "finance",       "keywords": ["cash",   "money",  "earn",   "profit", "fund"]},
    {"niche": "health",        "keywords": ["health", "fit",    "life",   "well",   "care"]},
    {"niche": "travel",        "keywords": ["travel", "trip",   "journey","globe",  "tour"]},
    {"niche": "lifestyle",     "keywords": ["style",  "living", "modern", "urban",  "chic"]},
    {"niche": "sports",        "keywords": ["sport",  "score",  "league", "arena",  "champ"]},
    {"niche": "education",     "keywords": ["learn",  "study",  "edu",    "skill",  "course"]},
]

# ── Website structures ────────────────────────────────────────
WEBSITE_STRUCTURES = [
    "{keyword}{number}.{tld}",
    "{keyword}-{word}.{tld}",
    "{word}{keyword}.{tld}",
    "the{keyword}hub.{tld}",
    "{keyword}daily.{tld}",
    "{keyword}zone.{tld}",
    "my{keyword}site.{tld}",
    "{keyword}world.{tld}",
    "pro{keyword}.{tld}",
    "{keyword}plus.{tld}",
]

FILLER_WORDS = [
    "hub", "pro", "zone", "plus", "max",
    "top", "best", "prime", "ultra", "mega",
    "go", "my", "the", "get", "now",
]

# ── Secure password patterns ──────────────────────────────────
SPECIAL_CHARS = ["!", "@", "#", "$", "%", "&", "*"]

# ── Test email domains ────────────────────────────────────────
TEST_EMAIL_DOMAINS = [
    "testmail.com",
    "example.com",
    "mailtest.org",
    "demomail.net",
    "testuser.io",
    "samplemail.com",
    "fakemail.org",
    "trialmail.net",
    "devmail.com",
    "qatest.org",
]

# ── Telegram username patterns ────────────────────────────────
TG_PREFIXES  = ["user", "pub", "media", "web", "net", "pro", "dev", "ad", "site", "online"]
TG_SUFFIXES  = ["101",  "pro", "hub",   "xyz", "media", "official", "real", "net", "web", "007"]

# ── Skype username patterns ───────────────────────────────────
SKYPE_PATTERNS = [
    "live:{first}{last}{num}",
    "{first}.{last}{num}",
    "{first}{last}.{num}",
    "{first}_{last}",
    "publisher.{first}{num}",
]


# ================================================================
#                  DATA GENERATOR CLASS
# ================================================================
@dataclass
class PublisherProfile:
    """Realistic Adsterra publisher test profile."""
    full_name:       str = ""
    first_name:      str = ""
    last_name:       str = ""
    email:           str = ""
    password:        str = ""
    country:         dict = field(default_factory=dict)
    website_url:     str = ""
    website_niche:   str = ""
    telegram:        str = ""
    skype:           str = ""
    generated_at:    str = ""

    def to_dict(self) -> dict:
        return {
            "full_name":     self.full_name,
            "email":         self.email,
            "password":      self.password,
            "country":       self.country.get("name", ""),
            "website_url":   self.website_url,
            "website_niche": self.website_niche,
            "telegram":      self.telegram,
            "skype":         self.skype,
            "generated_at":  self.generated_at,
        }


class AdsterraDataGenerator:
    """
    Generates 100% realistic Adsterra publisher
    registration profiles for testing purposes.
    """

    # ── Name Generator ────────────────────────────────────────
    @staticmethod
    def generate_name() -> tuple[str, str, str]:
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)
        full  = f"{first} {last}"
        return full, first, last

    # ── Password Generator ────────────────────────────────────
    @staticmethod
    def generate_password(length: int = 14) -> str:
        """
        Format: Word + Number + Special + Word + Number
        Example: Sunrise47@Thunder92
        """
        words = [
            "Alpha", "Beta", "Cyber", "Delta", "Echo",
            "Falcon", "Ghost", "Hunter", "Iron", "Jade",
            "Kilo", "Luna", "Maxim", "Nova", "Omega",
            "Phoenix", "Quest", "Raven", "Storm", "Tiger",
            "Ultra", "Viper", "Wolf", "Xenon", "Zephyr",
            "Blaze", "Cloud", "Dawn", "Edge", "Frost",
            "Glitch", "Haze", "Inferno", "Jolt", "Knight",
        ]
        word1   = random.choice(words)
        word2   = random.choice(words)
        num1    = random.randint(10, 99)
        num2    = random.randint(10, 99)
        special = random.choice(SPECIAL_CHARS)
        return f"{word1}{num1}{special}{word2}{num2}"

    # ── Email Generator ───────────────────────────────────────
    @staticmethod
    def generate_email(first: str, last: str) -> str:
        domain  = random.choice(TEST_EMAIL_DOMAINS)
        num     = random.randint(1, 999)
        sep     = random.choice([".", "_", ""])
        pattern = random.randint(1, 5)

        if pattern == 1:
            local = f"{first.lower()}{sep}{last.lower()}"
        elif pattern == 2:
            local = f"{first.lower()}{sep}{last.lower()}{num}"
        elif pattern == 3:
            local = f"{first.lower()[0]}{last.lower()}{num}"
        elif pattern == 4:
            local = f"{first.lower()}{num}"
        else:
            local = f"{first.lower()}{sep}{last.lower()[0]}{num}"

        return f"{local}@{domain}"

    # ── Website Generator ─────────────────────────────────────
    @staticmethod
    def generate_website(country: dict) -> tuple[str, str]:
        niche_data = random.choice(WEBSITE_NICHES)
        keyword    = random.choice(niche_data["keywords"])
        structure  = random.choice(WEBSITE_STRUCTURES)
        word       = random.choice(FILLER_WORDS)
        number     = random.randint(1, 999)
        tld        = random.choice([
            country["tld"], "com", "net", "org", "io", "co"
        ])

        domain = (
            structure
            .replace("{keyword}", keyword)
            .replace("{word}",    word)
            .replace("{number}",  str(number))
            .replace("{tld}",     tld)
        )

        # Clean up double dots or dashes
        domain = domain.replace("..", ".").replace("--", "-")
        url = f"https://www.{domain}"
        return url, niche_data["niche"]

    # ── Telegram Username Generator ───────────────────────────
    @staticmethod
    def generate_telegram(first: str, last: str) -> str:
        num     = random.randint(1, 9999)
        prefix  = random.choice(TG_PREFIXES)
        suffix  = random.choice(TG_SUFFIXES)
        pattern = random.randint(1, 5)

        if pattern == 1:
            return f"@{first.lower()}{last.lower()}{num}"
        elif pattern == 2:
            return f"@{prefix}_{first.lower()}{num}"
        elif pattern == 3:
            return f"@{first.lower()}_{suffix}"
        elif pattern == 4:
            return f"@{first.lower()}{last.lower()[0]}{num}"
        else:
            return f"@{prefix}{num}{suffix}"

    # ── Skype Username Generator ──────────────────────────────
    @staticmethod
    def generate_skype(first: str, last: str) -> str:
        num     = random.randint(1, 999)
        pattern = random.choice(SKYPE_PATTERNS)
        result  = (
            pattern
            .replace("{first}", first.lower())
            .replace("{last}",  last.lower())
            .replace("{num}",   str(num))
        )
        return result

    # ── Full Profile Generator ────────────────────────────────
    @classmethod
    def generate_profile(cls) -> PublisherProfile:
        full, first, last = cls.generate_name()
        country           = random.choice(COUNTRIES)
        website, niche    = cls.generate_website(country)

        return PublisherProfile(
            full_name     = full,
            first_name    = first,
            last_name     = last,
            email         = cls.generate_email(first, last),
            password      = cls.generate_password(),
            country       = country,
            website_url   = website,
            website_niche = niche,
            telegram      = cls.generate_telegram(first, last),
            skype         = cls.generate_skype(first, last),
            generated_at  = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    # ── Batch Generator ───────────────────────────────────────
    @classmethod
    def generate_batch(cls, count: int = 5) -> list[PublisherProfile]:
        profiles = []
        emails   = set()
        while len(profiles) < count:
            p = cls.generate_profile()
            if p.email not in emails:
                emails.add(p.email)
                profiles.append(p)
        return profiles


# ================================================================
#                      SESSION STORE
# ================================================================
@dataclass
class SessionStore:
    email:            Optional[str] = None
    password:         Optional[str] = None
    full_name:        Optional[str] = None
    website:          Optional[str] = None
    country:          Optional[str] = None
    telegram_user:    Optional[str] = None
    skype_user:       Optional[str] = None
    logged_in:        bool          = False
    signup_done:      bool          = False
    awaiting_confirm: bool          = False
    current_profile:  Optional[PublisherProfile] = None
    page:             Optional[Page]             = None
    browser:          Optional[Browser]          = None
    ctx:              Optional[BrowserContext]   = None
    _playwright:      object                     = None

    def __post_init__(self):
        self._lock = asyncio.Lock()

    @property
    def has_credentials(self) -> bool:
        return bool(self.email and self.password)

    @property
    def browser_alive(self) -> bool:
        return self.browser is not None

    async def full_logout(self) -> None:
        async with self._lock:
            self.email            = None
            self.password         = None
            self.full_name        = None
            self.website          = None
            self.country          = None
            self.telegram_user    = None
            self.skype_user       = None
            self.logged_in        = False
            self.signup_done      = False
            self.awaiting_confirm = False
            self.current_profile  = None
            await self._destroy_browser()

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
                    logger.warning("⚠️ Error closing %s: %s", label, exc)

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("⚠️ Playwright stop: %s", exc)

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
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_type(page: Page, selector: str, text: str) -> None:
    await page.click(selector)
    await human_delay(0.2, 0.6)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(40, 110))
    await human_delay(0.2, 0.6)


# ================================================================
#                  KEYBOARD FACTORY
# ================================================================
def main_menu(logged_in: bool = False) -> InlineKeyboardMarkup:
    if logged_in:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Create Smartlink",    callback_data="create_smartlink")],
            [InlineKeyboardButton("📊 Session Status",      callback_data="status")],
            [InlineKeyboardButton("🚪 Logout",              callback_data="logout")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login",                   callback_data="login")],
        [
            InlineKeyboardButton("🎲 Auto Sign Up",         callback_data="auto_signup"),
            InlineKeyboardButton("✍️ Manual Sign Up",       callback_data="manual_signup"),
        ],
        [InlineKeyboardButton("🎰 Generate Test Data",      callback_data="generate_data")],
        [InlineKeyboardButton("📊 Status",                  callback_data="status")],
    ])


def signup_confirm_keyboard(profile: PublisherProfile) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Use This Profile",        callback_data="confirm_signup")],
        [InlineKeyboardButton("🔄 Generate Another",        callback_data="auto_signup")],
        [InlineKeyboardButton("✍️ Edit Manually",           callback_data="manual_signup")],
        [InlineKeyboardButton("❌ Cancel",                  callback_data="cancel_signup")],
    ])


CONFIRM_LOGOUT_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Yes, Logout",              callback_data="logout_confirm"),
        InlineKeyboardButton("❌ Cancel",                   callback_data="logout_cancel"),
    ]
])

GENERATE_MORE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔄 Generate More",               callback_data="generate_data")],
    [InlineKeyboardButton("🎲 Auto Sign Up",                callback_data="auto_signup")],
    [InlineKeyboardButton("🏠 Main Menu",                   callback_data="main_menu")],
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
        logger.warning("safe_edit: %s", exc)


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("Notify: %s", exc)


async def delete_msg(update: Update) -> None:
    try:
        await update.message.delete()
    except Exception:
        pass


def format_profile_card(profile: PublisherProfile, title: str = "👤 Publisher Profile") -> str:
    """Format a profile into a beautiful Telegram message."""
    tier_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(
        profile.country.get("tier", 1), "🌍"
    )
    return (
        f"<b>{title}</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"👤 <b>Full Name</b>   : <code>{profile.full_name}</code>\n"
        f"📧 <b>Email</b>       : <code>{profile.email}</code>\n"
        f"🔑 <b>Password</b>    : <code>{profile.password}</code>\n"
        f"{tier_emoji} <b>Country</b>     : {profile.country.get('name', 'N/A')}\n"
        f"🌐 <b>Website</b>     : <code>{profile.website_url}</code>\n"
        f"📂 <b>Niche</b>       : {profile.website_niche.title()}\n"
        f"✈️ <b>Telegram</b>    : <code>{profile.telegram}</code>\n"
        f"💬 <b>Skype</b>       : <code>{profile.skype}</code>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🕐 Generated : {profile.generated_at}"
    )


# ================================================================
#                  PLAYWRIGHT ENGINE
# ================================================================
async def get_page() -> Page:
    if SESSION.page and not SESSION.page.is_closed():
        return SESSION.page

    logger.info("🌐 Launching browser…")
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
async def automation_signup(profile: PublisherProfile) -> dict:
    """
    Full Adsterra publisher signup automation
    using a generated or manual profile.
    """
    try:
        page = await get_page()
        logger.info("📝 Navigating to signup…")
        await page.goto(ADSTERRA_SIGNUP_URL, wait_until="networkidle")
        await human_delay(2.0, 4.0)

        # ── Full Name ─────────────────────────────────────────
        for sel in [
            'input[name="name"]',
            'input[name="full_name"]',
            'input[name="fullName"]',
            'input[placeholder*="name" i]',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, profile.full_name)
                    logger.info("👤 Name: %s", profile.full_name)
                    break
            except Exception:
                continue

        await human_delay(0.5, 1.0)

        # ── Email ─────────────────────────────────────────────
        for sel in [
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="email" i]',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, profile.email)
                    logger.info("📧 Email: %s", profile.email)
                    break
            except Exception:
                continue

        await human_delay(0.5, 1.0)

        # ── Password ──────────────────────────────────────────
        for sel in [
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="password" i]',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, profile.password)
                    logger.info("🔑 Password filled")
                    break
            except Exception:
                continue

        await human_delay(0.5, 1.0)

        # ── Confirm Password ──────────────────────────────────
        for sel in [
            'input[name="password_confirmation"]',
            'input[name="confirm_password"]',
            'input[name="confirmPassword"]',
            'input[placeholder*="confirm" i]',
            'input[placeholder*="repeat" i]',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, profile.password)
                    logger.info("🔑 Confirm password filled")
                    break
            except Exception:
                continue

        await human_delay(0.5, 1.0)

        # ── Website ───────────────────────────────────────────
        for sel in [
            'input[name="website"]',
            'input[name="site_url"]',
            'input[name="url"]',
            'input[placeholder*="website" i]',
            'input[placeholder*="url" i]',
            'input[placeholder*="site" i]',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, profile.website_url)
                    logger.info("🌐 Website: %s", profile.website_url)
                    break
            except Exception:
                continue

        await human_delay(0.5, 1.0)

        # ── Country Selector ──────────────────────────────────
        for sel in [
            'select[name="country"]',
            'select[name="country_id"]',
            '[class*="country"] select',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    # Try by value (country code)
                    try:
                        await page.select_option(
                            sel,
                            value=profile.country.get("code", "US"),
                        )
                    except Exception:
                        # Try by label (country name)
                        await page.select_option(
                            sel,
                            label=profile.country.get("name", "United States"),
                        )
                    logger.info("🌍 Country: %s", profile.country.get("name"))
                    await human_delay(0.5, 1.0)
                    break
            except Exception:
                continue

        # ── Telegram / Skype / Messenger ──────────────────────
        messenger_fields = {
            'input[name="telegram"]':           profile.telegram,
            'input[name="skype"]':              profile.skype,
            'input[placeholder*="telegram" i]': profile.telegram,
            'input[placeholder*="skype" i]':    profile.skype,
            'input[placeholder*="messenger" i]':profile.telegram,
            'input[placeholder*="contact" i]':  profile.telegram,
        }
        for sel, value in messenger_fields.items():
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, value)
                    logger.info("💬 Messenger filled: %s", value)
                    break
            except Exception:
                continue

        await human_delay(1.0, 2.0)

        # ── Traffic source / How did you hear ─────────────────
        for sel in [
            'select[name="traffic_source"]',
            'select[name="source"]',
            'select[name="how_did_you_hear"]',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    await page.select_option(sel, index=1)
                    await human_delay(0.5, 1.0)
                    break
            except Exception:
                continue

        # ── Terms Checkbox ────────────────────────────────────
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
                    if not await cb.is_checked():
                        await cb.check()
                        logger.info("☑️ Terms checked")
                    break
            except Exception:
                continue

        await human_delay(1.0, 2.0)

        # ── Submit ────────────────────────────────────────────
        for sel in [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Register")',
            'button:has-text("Sign Up")',
            'button:has-text("Create Account")',
            'button:has-text("Get Started")',
            'button:has-text("Join")',
        ]:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    logger.info("🖱️ Form submitted")
                    break
            except Exception:
                continue

        await page.wait_for_load_state("networkidle")
        await human_delay(4.0, 7.0)

        current_url = page.url.lower()
        page_text   = (await page.inner_text("body")).lower()

        # ── Detect confirmation needed ────────────────────────
        if any(k in current_url or k in page_text for k in [
            "confirm", "verify", "verification",
            "check your email", "activation", "sent",
        ]):
            SESSION.awaiting_confirm = True
            SESSION.signup_done      = True
            return {"success": True, "needs_confirm": True,
                    "message": "Signup done! Check your email."}

        # ── Detect direct login ───────────────────────────────
        if any(k in current_url for k in ["dashboard", "publisher", "smartlink"]):
            SESSION.logged_in   = True
            SESSION.signup_done = True
            return {"success": True, "needs_confirm": False,
                    "message": "Signup & logged in!"}

        # ── Detect errors ─────────────────────────────────────
        for sel in [".alert-danger", ".error-message", "[class*='error']", "p.text-red"]:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    err = (await el.first.inner_text()).strip()
                    if err:
                        return {"success": False, "needs_confirm": False,
                                "message": f"Error: {err}"}
            except Exception:
                continue

        return {"success": False, "needs_confirm": False,
                "message": "Signup outcome unclear. Check email or try again."}

    except Exception as exc:
        logger.exception("Signup error")
        return {"success": False, "needs_confirm": False, "message": str(exc)}


# ================================================================
#              CORE AUTOMATION — CONFIRM EMAIL
# ================================================================
async def automation_confirm(confirm_url: str) -> dict:
    try:
        page = await get_page()
        logger.info("🔗 Opening confirmation: %s", confirm_url)
        await page.goto(confirm_url, wait_until="networkidle")
        await human_delay(3.0, 6.0)

        url_  = page.url.lower()
        text_ = (await page.inner_text("body")).lower()

        if any(k in url_ or k in text_ for k in [
            "verified", "confirmed", "success",
            "congratulation", "dashboard", "welcome",
        ]):
            SESSION.awaiting_confirm = False
            return {"success": True, "message": "Email confirmed!"}

        if any(k in text_ for k in ["expired", "invalid", "already"]):
            return {"success": False,
                    "message": "Link expired or already used."}

        return {"success": True,
                "message": "Link opened. Proceeding to login…"}

    except Exception as exc:
        logger.exception("Confirm error")
        return {"success": False, "message": str(exc)}


# ================================================================
#              CORE AUTOMATION — LOGIN
# ================================================================
async def automation_login() -> dict:
    try:
        page = await get_page()
        logger.info("🔑 Logging in…")
        await page.goto(ADSTERRA_LOGIN_URL, wait_until="networkidle")
        await human_delay(2.0, 4.0)

        # Email
        for sel in ['input[type="email"]', 'input[name="email"]',
                    'input[placeholder*="email" i]']:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.email)
                    break
            except Exception:
                continue

        await human_delay(0.8, 1.5)

        # Password
        for sel in ['input[type="password"]', 'input[name="password"]',
                    'input[placeholder*="password" i]']:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, SESSION.password)
                    break
            except Exception:
                continue

        await human_delay(1.0, 2.0)

        # Submit
        for sel in ['button[type="submit"]', 'button:has-text("Login")',
                    'button:has-text("Sign in")', 'button:has-text("Log in")']:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    break
            except Exception:
                continue

        await page.wait_for_load_state("networkidle")
        await human_delay(4.0, 7.0)

        url_ = page.url.lower()
        success_signals = [
            "dashboard" in url_, "publisher" in url_,
            "smartlink" in url_, "/home" in url_,
            await page.locator("text=Dashboard").count() > 0,
            await page.locator("text=Log out").count()  > 0,
        ]

        if any(success_signals):
            SESSION.logged_in = True
            return {"success": True, "message": "Login successful"}

        for sel in [".alert-danger", ".error-message", "[class*='error']"]:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    err = (await el.first.inner_text()).strip()
                    if err:
                        return {"success": False, "message": err}
            except Exception:
                continue

        return {"success": False,
                "message": "Login failed — wrong credentials or CAPTCHA."}

    except Exception as exc:
        logger.exception("Login error")
        return {"success": False, "message": str(exc)}


# ================================================================
#              CORE AUTOMATION — CREATE SMARTLINK
# ================================================================
async def automation_create_smartlink() -> dict:
    try:
        page = await get_page()
        await page.goto(ADSTERRA_SMARTLINK_URL, wait_until="networkidle")
        await human_delay(3.0, 5.5)

        for sel in ["text=Create Smartlink", "text=New Smartlink",
                    "button:has-text('Create')", "a:has-text('Create')"]:
            try:
                if await page.locator(sel).count() > 0:
                    await page.click(sel)
                    break
            except Exception:
                continue

        await human_delay(2.5, 4.5)
        name = f"AutoLink_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for sel in ['input[name="name"]', 'input[placeholder*="name" i]']:
            try:
                if await page.locator(sel).count() > 0:
                    await human_type(page, sel, name)
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
                        return {"success": True, "url": url, "name": name,
                                "message": "Created!"}
            except Exception:
                continue

        return {"success": True, "url": None, "name": name,
                "message": "Created — check dashboard for URL."}

    except Exception as exc:
        logger.exception("Smartlink error")
        return {"success": False, "url": None, "name": None, "message": str(exc)}


# ================================================================
#                  COMMAND HANDLERS
# ================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user        = update.effective_user
    status_icon = "🟢 Active" if SESSION.logged_in else "🔴 Not logged in"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"

    text = (
        f"👋 <b>Hello, {user.first_name}!</b>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🤖 <b>Adsterra Publisher Bot</b>\n"
        f"   God Level Edition v3.0\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"📌 Session : {status_icon}\n"
        f"👤 Account : {account}\n"
        f"🕐 Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>Features:</b>\n"
        f"  🎲 Auto-generate realistic test data\n"
        f"  🤖 Fully automated signup\n"
        f"  📧 Email confirmation handler\n"
        f"  🔐 Auto re-login after confirm\n"
        f"  🔗 Smartlink creation\n\n"
        f"Choose below 👇"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_icon = "🟢 Active"  if SESSION.logged_in    else "🔴 Inactive"
    browser_st  = "🟢 Running" if SESSION.browser_alive else "⚫ Closed"
    confirm_st  = "⏳ Pending" if SESSION.awaiting_confirm else "✅ OK"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"

    profile_row = ""
    if SESSION.current_profile:
        p = SESSION.current_profile
        profile_row = (
            f"\n<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"🎲 <b>Current Profile</b>\n"
            f"👤 {p.full_name}\n"
            f"🌍 {p.country.get('name', 'N/A')}\n"
            f"🌐 {p.website_url}\n"
        )

    text = (
        f"<b>📊 Live Session Report</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔐 Login     : {status_icon}\n"
        f"👤 Account   : {account}\n"
        f"🌐 Browser   : {browser_st}\n"
        f"📧 Confirmed : {confirm_st}\n"
        f"🕐 Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        f"{profile_row}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ <b>Cancelled.</b>",
        parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#              INLINE — GENERATE TEST DATA
# ================================================================
async def inline_generate_data(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    profiles = AdsterraDataGenerator.generate_batch(3)
    text     = "🎰 <b>Generated Test Publisher Profiles</b>\n\n"

    for i, p in enumerate(profiles, 1):
        tier_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(p.country.get("tier", 1), "🌍")
        text += (
            f"<b>── Profile {i} ──────────────────</b>\n"
            f"👤 <b>Name</b>     : <code>{p.full_name}</code>\n"
            f"📧 <b>Email</b>    : <code>{p.email}</code>\n"
            f"🔑 <b>Password</b> : <code>{p.password}</code>\n"
            f"{tier_emoji} <b>Country</b>  : {p.country.get('name')}\n"
            f"🌐 <b>Website</b>  : <code>{p.website_url}</code>\n"
            f"📂 <b>Niche</b>    : {p.website_niche.title()}\n"
            f"✈️ <b>Telegram</b> : <code>{p.telegram}</code>\n"
            f"💬 <b>Skype</b>    : <code>{p.skype}</code>\n\n"
        )

    text += (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<i>⚠️ Test data only — example domains.\n"
        f"Use 🎲 Auto Sign Up to register with a\n"
        f"freshly generated profile!</i>"
    )

    await safe_edit(query, text, keyboard=GENERATE_MORE_KB)
    return ConversationHandler.END


# ================================================================
#              INLINE — MAIN MENU BUTTON
# ================================================================
async def inline_main_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await safe_edit(
        query,
        "🏠 <b>Main Menu</b>\nChoose an option:",
        keyboard=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#         CONVERSATION — AUTO SIGNUP (generated profile)
# ================================================================
async def auto_signup_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    if SESSION.logged_in:
        await safe_edit(
            query,
            "✅ Already logged in. Logout first.",
            keyboard=main_menu(True),
        )
        return ConversationHandler.END

    # Generate fresh profile
    profile = AdsterraDataGenerator.generate_profile()
    SESSION.current_profile = profile

    card = format_profile_card(profile, "🎲 Generated Profile — Ready to Register")
    card += (
        "\n\n<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "⚡ <b>This profile will be used to register\n"
        "on Adsterra automatically.</b>\n\n"
        "Review and confirm below:"
    )

    await safe_edit(query, card, keyboard=signup_confirm_keyboard(profile))
    return STATE_SIGNUP_CONFIRM


async def auto_signup_confirmed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    profile = SESSION.current_profile
    if not profile:
        await safe_edit(
            query, "❌ No profile found. Try again.",
            keyboard=main_menu(False),
        )
        return ConversationHandler.END

    # Store to session
    SESSION.email         = profile.email
    SESSION.password      = profile.password
    SESSION.full_name     = profile.full_name
    SESSION.website       = profile.website_url
    SESSION.country       = profile.country.get("name")
    SESSION.telegram_user = profile.telegram
    SESSION.skype_user    = profile.skype

    await safe_edit(
        query,
        (
            f"⏳ <b>Registering on Adsterra…</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 {profile.full_name}\n"
            f"📧 {profile.email}\n"
            f"🌍 {profile.country.get('name')}\n"
            f"🌐 {profile.website_url}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"🌐 Launching browser…\n"
            f"📝 Filling form…\n"
            f"⏳ Submitting…\n\n"
            f"<i>Takes 20–40 seconds…</i>"
        ),
    )

    result = await automation_signup(profile)
    await _handle_signup_result(query, context, result, profile)
    return STATE_CONFIRM_LINK if result.get("needs_confirm") else ConversationHandler.END


async def auto_signup_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    SESSION.current_profile = None
    await safe_edit(
        query, "❌ <b>Signup cancelled.</b>",
        keyboard=main_menu(False),
    )
    return ConversationHandler.END


# ================================================================
#         CONVERSATION — MANUAL SIGNUP
# ================================================================
async def manual_signup_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    if SESSION.logged_in:
        await safe_edit(
            query, "✅ Already logged in. Logout first.",
            keyboard=main_menu(True),
        )
        return ConversationHandler.END

    # Pre-fill with generated data as suggestion
    suggestion = AdsterraDataGenerator.generate_profile()
    SESSION.current_profile = suggestion

    await safe_edit(
        query,
        (
            "✍️ <b>Manual Sign Up</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "👤 <b>Step 1/6</b> — Full Name\n\n"
            f"💡 Suggestion: <code>{suggestion.full_name}</code>\n\n"
            "Send your <b>full name</b> or copy the suggestion:\n\n"
            "<i>/cancel to abort</i>"
        ),
    )
    return STATE_MANUAL_NAME


async def manual_receive_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text(
            "⚠️ Too short. Send your full name:"
        )
        return STATE_MANUAL_NAME

    SESSION.full_name = name
    p = SESSION.current_profile

    await update.message.reply_text(
        (
            "✅ <b>Name saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "📧 <b>Step 2/6</b> — Email\n\n"
            f"💡 Suggestion: <code>{p.email if p else 'N/A'}</code>\n\n"
            "Send your <b>email address</b>:\n\n"
            "<i>/cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_MANUAL_EMAIL


async def manual_receive_email(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("⚠️ Invalid email. Try again:")
        return STATE_MANUAL_EMAIL

    SESSION.email = email
    await delete_msg(update)
    p = SESSION.current_profile

    await update.message.reply_text(
        (
            "✅ <b>Email saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🔑 <b>Step 3/6</b> — Password\n\n"
            f"💡 Suggestion: <code>{p.password if p else 'N/A'}</code>\n\n"
            "Send your <b>password</b> (min 8 chars):\n"
            "<i>Deleted instantly. /cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_MANUAL_PASSWORD


async def manual_receive_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    password = update.message.text.strip()
    await delete_msg(update)

    if len(password) < 8:
        await update.message.reply_text(
            "⚠️ Min 8 characters. Try again:"
        )
        return STATE_MANUAL_PASSWORD

    SESSION.password = password
    p = SESSION.current_profile

    await update.message.reply_text(
        (
            "✅ <b>Password saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🌐 <b>Step 4/6</b> — Website URL\n\n"
            f"💡 Suggestion: <code>{p.website_url if p else 'N/A'}</code>\n\n"
            "Send your <b>website URL</b> or type "
            "<code>skip</code>:\n\n"
            "<i>/cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_MANUAL_WEBSITE


async def manual_receive_website(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    if text.lower() == "skip":
        p = SESSION.current_profile
        SESSION.website = p.website_url if p else ""
    else:
        SESSION.website = text if text.startswith("http") else f"https://{text}"

    p = SESSION.current_profile
    await update.message.reply_text(
        (
            "✅ <b>Website saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🌍 <b>Step 5/6</b> — Country\n\n"
            f"💡 Suggestion: <code>{p.country.get('name') if p else 'United States'}</code>\n\n"
            "Send your <b>country name</b> or type "
            "<code>skip</code>:\n\n"
            "<i>/cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_MANUAL_COUNTRY


async def manual_receive_country(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    if text.lower() == "skip":
        p = SESSION.current_profile
        SESSION.country = p.country.get("name") if p else "United States"
    else:
        SESSION.country = text

    p = SESSION.current_profile
    await update.message.reply_text(
        (
            "✅ <b>Country saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "✈️ <b>Step 6/6</b> — Telegram / Skype\n\n"
            f"💡 Suggestion: <code>{p.telegram if p else '@username'}</code>\n\n"
            "Send your <b>Telegram username</b> or Skype,\n"
            "or type <code>skip</code>:\n\n"
            "<i>/cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_MANUAL_TELEGRAM


async def manual_receive_telegram(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    p    = SESSION.current_profile

    if text.lower() == "skip":
        SESSION.telegram_user = p.telegram if p else ""
        SESSION.skype_user    = p.skype    if p else ""
    else:
        SESSION.telegram_user = text
        SESSION.skype_user    = text

    # Build profile from manual input
    country_data = next(
        (c for c in COUNTRIES if c["name"].lower() == (SESSION.country or "").lower()),
        {"name": SESSION.country or "United States", "code": "US", "tld": "com", "tier": 1},
    )

    profile = PublisherProfile(
        full_name     = SESSION.full_name     or "",
        first_name    = (SESSION.full_name or "").split()[0] if SESSION.full_name else "",
        last_name     = (SESSION.full_name or "").split()[-1] if SESSION.full_name else "",
        email         = SESSION.email         or "",
        password      = SESSION.password      or "",
        country       = country_data,
        website_url   = SESSION.website       or "",
        website_niche = "general",
        telegram      = SESSION.telegram_user or "",
        skype         = SESSION.skype_user    or "",
        generated_at  = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    SESSION.current_profile = profile

    msg = await update.message.reply_text(
        (
            "⏳ <b>Registering on Adsterra…</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 {profile.full_name}\n"
            f"📧 {profile.email}\n"
            f"🌍 {country_data['name']}\n"
            f"🌐 {profile.website_url}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"🌐 Launching browser…\n"
            f"📝 Filling form…\n"
            f"⏳ Submitting…\n\n"
            f"<i>Takes 20–40 seconds…</i>"
        ),
        parse_mode="HTML",
    )

    result = await automation_signup(profile)
    await _handle_signup_result_msg(msg, context, result, profile)

    return STATE_CONFIRM_LINK if result.get("needs_confirm") else ConversationHandler.END


# ================================================================
#         SHARED SIGNUP RESULT HANDLER
# ================================================================
async def _handle_signup_result(query, context, result, profile):
    if result["success"] and result["needs_confirm"]:
        text = (
            f"✅ <b>Account Created!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 {profile.full_name}\n"
            f"📧 <code>{profile.email}</code>\n"
            f"🔑 <code>{profile.password}</code>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"📬 <b>Confirmation email sent!</b>\n\n"
            f"Steps:\n"
            f"1️⃣ Check inbox for <code>{profile.email}</code>\n"
            f"2️⃣ Open the confirmation email\n"
            f"3️⃣ <b>Copy the confirmation link</b>\n"
            f"4️⃣ Paste it here in this chat\n\n"
            f"<i>Bot will open it automatically and re-login!</i>"
        )
        await safe_edit(query, text)
        await notify_admin(
            context,
            f"📝 <b>New Signup</b>\n"
            f"👤 {profile.full_name}\n"
            f"📧 <code>{profile.email}</code>\n"
            f"⏳ Awaiting confirmation",
        )

    elif result["success"] and not result["needs_confirm"]:
        text = (
            f"🎉 <b>Registered & Logged In!</b>\n\n"
            f"👤 <code>{profile.email}</code>\n\n"
            f"Use 🔗 Create Smartlink to begin!"
        )
        await safe_edit(query, text, keyboard=main_menu(True))

    else:
        SESSION.email = SESSION.password = None
        text = (
            f"❌ <b>Signup Failed</b>\n\n"
            f"⚠️ {result['message']}\n\n"
            f"Try again with a different profile."
        )
        await safe_edit(query, text, keyboard=main_menu(False))


async def _handle_signup_result_msg(msg, context, result, profile):
    if result["success"] and result["needs_confirm"]:
        text = (
            f"✅ <b>Account Created!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"📧 <code>{profile.email}</code>\n"
            f"🔑 <code>{profile.password}</code>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"📬 <b>Confirmation email sent!</b>\n\n"
            f"1️⃣ Check inbox for <code>{profile.email}</code>\n"
            f"2️⃣ Copy the confirmation link\n"
            f"3️⃣ Paste it here\n\n"
            f"<i>Bot handles the rest automatically!</i>"
        )
        await msg.edit_text(text, parse_mode="HTML")
        await notify_admin(
            context,
            f"📝 <b>New Signup</b>\n👤 {profile.full_name}\n"
            f"📧 <code>{profile.email}</code>",
        )

    elif result["success"]:
        text = (
            f"🎉 <b>Registered & Logged In!</b>\n\n"
            f"👤 <code>{profile.email}</code>"
        )
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=main_menu(True),
        )
    else:
        SESSION.email = SESSION.password = None
        await msg.edit_text(
            f"❌ <b>Signup Failed</b>\n\n⚠️ {result['message']}",
            parse_mode="HTML",
            reply_markup=main_menu(False),
        )


# ================================================================
#          CONVERSATION — EMAIL CONFIRMATION LINK
# ================================================================
async def confirm_receive_link(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    raw  = update.message.text.strip()
    urls = re.findall(r'https?://[^\s]+', raw)
    url  = urls[0] if urls else raw

    if not url.startswith("http"):
        await update.message.reply_text(
            "⚠️ <b>Not a valid URL.</b>\n"
            "Paste the full confirmation link (starts with https://):",
            parse_mode="HTML",
        )
        return STATE_CONFIRM_LINK

    msg = await update.message.reply_text(
        (
            "⏳ <b>Opening confirmation link…</b>\n\n"
            f"🔗 <code>{url[:55]}{'…' if len(url)>55 else ''}</code>\n\n"
            "🌐 Loading in browser…\n"
            "✅ Verifying account…\n\n"
            "<i>Please wait…</i>"
        ),
        parse_mode="HTML",
    )

    result = await automation_confirm(url)

    if result["success"]:
        await msg.edit_text(
            (
                "✅ <b>Confirmed! Auto-logging in…</b>\n\n"
                "🔑 Using saved credentials…\n"
                "<i>15–20 seconds…</i>"
            ),
            parse_mode="HTML",
        )

        await human_delay(2.0, 4.0)
        await SESSION._destroy_browser()
        login_result = await automation_login()

        if login_result["success"]:
            p = SESSION.current_profile
            text = (
                f"🎉 <b>Account Confirmed & Logged In!</b>\n\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"👤 {p.full_name if p else SESSION.full_name}\n"
                f"📧 <code>{SESSION.email}</code>\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                f"✅ Account fully active!\n"
                f"Use 🔗 <b>Create Smartlink</b> to earn! 🎉"
            )
            await notify_admin(
                context,
                f"🎉 <b>Confirmed + Logged In</b>\n"
                f"📧 <code>{SESSION.email}</code>",
            )
            await msg.edit_text(
                text, parse_mode="HTML",
                reply_markup=main_menu(True),
            )
            return ConversationHandler.END

        else:
            await msg.edit_text(
                "✅ <b>Confirmed!</b> Auto-login failed.\n\n"
                "Please send your <b>password</b> again:\n"
                "<i>Deleted instantly.</i>",
                parse_mode="HTML",
            )
            return STATE_RELOGIN_PASSWORD

    else:
        await msg.edit_text(
            f"❌ <b>Confirmation Failed</b>\n\n"
            f"⚠️ {result['message']}\n\n"
            f"Send the correct link or use /start.",
            parse_mode="HTML",
            reply_markup=main_menu(False),
        )
        return STATE_CONFIRM_LINK


# ================================================================
#          CONVERSATION — RE-LOGIN AFTER CONFIRM
# ================================================================
async def relogin_receive_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    SESSION.password = update.message.text.strip()
    await delete_msg(update)

    msg = await update.message.reply_text(
        "⏳ <b>Logging in…</b>", parse_mode="HTML"
    )

    await SESSION._destroy_browser()
    result = await automation_login()

    if result["success"]:
        text = (
            f"✅ <b>Logged In!</b>\n\n"
            f"📧 <code>{SESSION.email}</code>\n"
            f"Use 🔗 Create Smartlink!"
        )
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=main_menu(True),
        )
    else:
        SESSION.password = None
        await msg.edit_text(
            f"❌ <b>Failed</b>\n\n⚠️ {result['message']}\n\nUse /start.",
            parse_mode="HTML",
            reply_markup=main_menu(False),
        )
    return ConversationHandler.END


# ================================================================
#         CONVERSATION — LOGIN FLOW
# ================================================================
async def login_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    if SESSION.logged_in:
        await safe_edit(
            query,
            f"✅ Already logged in as <code>{SESSION.email}</code>.",
            keyboard=main_menu(True),
        )
        return ConversationHandler.END

    await safe_edit(
        query,
        (
            "🔐 <b>Login to Adsterra</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "📧 <b>Step 1/2</b> — Email\n\n"
            "Send your <b>email address</b>:\n\n"
            "<i>/cancel to abort</i>"
        ),
    )
    return STATE_LOGIN_EMAIL


async def login_receive_email(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    email = update.message.text.strip()
    if "@" not in email or "." not in email:
        await update.message.reply_text("⚠️ Invalid email:")
        return STATE_LOGIN_EMAIL

    SESSION.email = email
    await delete_msg(update)

    await update.message.reply_text(
        (
            "✅ <b>Email saved!</b>\n\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "🔑 <b>Step 2/2</b> — Password\n\n"
            "Send your <b>password</b>:\n"
            "<i>Deleted instantly. /cancel to abort</i>"
        ),
        parse_mode="HTML",
    )
    return STATE_LOGIN_PASSWORD


async def login_receive_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    SESSION.password = update.message.text.strip()
    await delete_msg(update)

    msg = await update.message.reply_text(
        "⏳ <b>Logging in…</b>\n\n<i>15–30 seconds…</i>",
        parse_mode="HTML",
    )

    result = await automation_login()

    if result["success"]:
        text = (
            f"✅ <b>Login Successful!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"📧 <code>{SESSION.email}</code>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>"
        )
        await notify_admin(
            context,
            f"🟢 <b>Login</b>\n📧 <code>{SESSION.email}</code>",
        )
    else:
        SESSION.email = SESSION.password = None
        text = (
            f"❌ <b>Login Failed</b>\n\n"
            f"⚠️ {result['message']}"
        )

    await msg.edit_text(
        text, parse_mode="HTML",
        reply_markup=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#         CONVERSATION — LOGOUT FLOW
# ================================================================
async def logout_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    if not SESSION.email and not SESSION.logged_in:
        await safe_edit(
            query, "⚠️ No active session.",
            keyboard=main_menu(False),
        )
        return ConversationHandler.END

    account = f"<code>{SESSION.email}</code>" if SESSION.email else "Unknown"
    await safe_edit(
        query,
        (
            f"🚪 <b>Confirm Logout</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"👤 {account}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"This will clear ALL session data.\n\n"
            f"<b>Are you sure?</b>"
        ),
        keyboard=CONFIRM_LOGOUT_KB,
    )
    return STATE_LOGOUT_CONFIRM


async def logout_confirmed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query     = update.callback_query
    await query.answer()
    old_email = SESSION.email or "Unknown"

    await safe_edit(query, "⏳ <b>Logging out…</b>")
    await SESSION.full_logout()

    await safe_edit(
        query,
        (
            f"✅ <b>Logged Out!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"📧 <code>{old_email}</code>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
            f"🌐 Browser : Closed\n"
            f"🔐 Session : Cleared\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>"
        ),
        keyboard=main_menu(False),
    )
    await notify_admin(
        context,
        f"🔴 <b>Logout</b>\n📧 <code>{old_email}</code>",
    )
    return ConversationHandler.END


async def logout_cancelled(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await safe_edit(
        query,
        "✅ <b>Logout cancelled.</b>",
        keyboard=main_menu(SESSION.logged_in),
    )
    return ConversationHandler.END


# ================================================================
#         INLINE — CREATE SMARTLINK + STATUS
# ================================================================
async def inline_create_smartlink(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    if not SESSION.logged_in:
        await safe_edit(
            query,
            "🔴 <b>Not logged in!</b> Login first.",
            keyboard=main_menu(False),
        )
        return ConversationHandler.END

    await safe_edit(
        query,
        "⏳ <b>Creating Smartlink…</b>\n\n<i>20–40 seconds…</i>",
    )

    result = await automation_create_smartlink()

    if result["success"]:
        url_line = (
            f"\n🔗 <code>{result['url']}</code>"
            if result.get("url")
            else "\n⚠️ Check dashboard for URL."
        )
        text = (
            f"🎉 <b>Smartlink Created!</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"📛 <code>{result.get('name', 'N/A')}</code>"
            f"{url_line}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>"
        )
        await notify_admin(
            context,
            f"🔗 <b>Smartlink</b>\n📧 <code>{SESSION.email}</code>\n"
            f"🔗 {result.get('url', 'N/A')}",
        )
    else:
        text = f"❌ <b>Failed</b>\n\n⚠️ {result['message']}"

    await safe_edit(query, text, keyboard=main_menu(SESSION.logged_in))
    return ConversationHandler.END


async def inline_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    status_icon = "🟢 Active"  if SESSION.logged_in    else "🔴 Inactive"
    browser_st  = "🟢 Running" if SESSION.browser_alive else "⚫ Closed"
    confirm_st  = "⏳ Pending" if SESSION.awaiting_confirm else "✅ OK"
    account     = f"<code>{SESSION.email}</code>" if SESSION.email else "N/A"

    text = (
        f"<b>📊 Session Status</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"🔐 Login     : {status_icon}\n"
        f"👤 Account   : {account}\n"
        f"🌐 Browser   : {browser_st}\n"
        f"📧 Confirmed : {confirm_st}\n"
        f"🕐 Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await safe_edit(query, text, keyboard=main_menu(SESSION.logged_in))
    return ConversationHandler.END


# ================================================================
#                     ERROR HANDLER
# ================================================================
async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.error("Error: %s", context.error, exc_info=context.error)


# ================================================================
#                          MAIN
# ================================================================
def main() -> None:
    logger.info("=" * 60)
    logger.info("  ADSTERRA BOT v3.0 — God Level Edition")
    logger.info("  Auto Data Generator + Full Signup Automation")
    logger.info("=" * 60)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Login Conversation ────────────────────────────────────
    login_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(login_entry, pattern="^login$")],
        states={
            STATE_LOGIN_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, login_receive_email)],
            STATE_LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_receive_password)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False, allow_reentry=True,
    )

    # ── Auto Signup Conversation ──────────────────────────────
    auto_signup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(auto_signup_entry, pattern="^auto_signup$")],
        states={
            STATE_SIGNUP_CONFIRM: [
                CallbackQueryHandler(auto_signup_confirmed, pattern="^confirm_signup$"),
                CallbackQueryHandler(auto_signup_entry,     pattern="^auto_signup$"),
                CallbackQueryHandler(auto_signup_cancel,    pattern="^cancel_signup$"),
            ],
            STATE_CONFIRM_LINK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_receive_link)],
            STATE_RELOGIN_PASSWORD:[MessageHandler(filters.TEXT & ~filters.COMMAND, relogin_receive_password)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False, allow_reentry=True,
    )

    # ── Manual Signup Conversation ────────────────────────────
    manual_signup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(manual_signup_entry, pattern="^manual_signup$")],
        states={
            STATE_MANUAL_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_receive_name)],
            STATE_MANUAL_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_receive_email)],
            STATE_MANUAL_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_receive_password)],
            STATE_MANUAL_WEBSITE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_receive_website)],
            STATE_MANUAL_COUNTRY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_receive_country)],
            STATE_MANUAL_TELEGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_receive_telegram)],
            STATE_CONFIRM_LINK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_receive_link)],
            STATE_RELOGIN_PASSWORD:[MessageHandler(filters.TEXT & ~filters.COMMAND, relogin_receive_password)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False, allow_reentry=True,
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
        per_message=False, allow_reentry=True,
    )

    # ── Register All ──────────────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(login_conv)
    app.add_handler(auto_signup_conv)
    app.add_handler(manual_signup_conv)
    app.add_handler(logout_conv)
    app.add_handler(CallbackQueryHandler(inline_generate_data,    pattern="^generate_data$"))
    app.add_handler(CallbackQueryHandler(inline_create_smartlink, pattern="^create_smartlink$"))
    app.add_handler(CallbackQueryHandler(inline_status,           pattern="^status$"))
    app.add_handler(CallbackQueryHandler(inline_main_menu,        pattern="^main_menu$"))
    app.add_error_handler(error_handler)

    logger.info("✅ Bot is live! Send /start in Telegram.")
    logger.info("=" * 60)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
