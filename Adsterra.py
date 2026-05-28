# adsterra_telegram_bot.py
import asyncio
import random
from datetime import datetime
import json
import os

from playwright.async_api import async_playwright
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# ===================== CONFIG =====================
TELEGRAM_BOT_TOKEN = "8766573450:AAGDkv16RZOKPb8jqEZTGVoO5SsjmYnK6zI"
TELEGRAM_CHAT_ID = "3797306274"

EMAIL = None
PASSWORD = None
CURRENT_PAGE = None
BROWSER = None
CONTEXT = None

# States for conversation
EMAIL_STATE, PASSWORD_STATE = range(2)

# Anti-detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
]

async def human_delay(min_sec=1.2, max_sec=4.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def human_type(page, selector, text):
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(25, 75))
    await human_delay(0.5, 1.2)

async def send_message(context, message):
    try:
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception:
        pass

# ===================== TELEGRAM COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Login to Adsterra", callback_data="login")],
        [InlineKeyboardButton("Create Smartlink", callback_data="create_smartlink")],
        [InlineKeyboardButton("Logout", callback_data="logout")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Adsterra Automation Bot Ready!\n\n"
        "Choose an option below:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ FIX: Declare ALL globals at the TOP of the function,
    #         before any reference to these variables
    global EMAIL, PASSWORD, CURRENT_PAGE, BROWSER, CONTEXT

    query = update.callback_query
    await query.answer()

    if query.data == "login":
        await query.edit_message_text("Please send me your Adsterra email:")
        return EMAIL_STATE

    elif query.data == "create_smartlink":
        if not EMAIL or not PASSWORD:
            await query.edit_message_text("You must login first! Use the Login button.")
            return ConversationHandler.END
        await create_smartlink(update, context)
        return ConversationHandler.END

    elif query.data == "logout":
        EMAIL = None
        PASSWORD = None
        if CURRENT_PAGE:
            await CURRENT_PAGE.close()
        if CONTEXT:
            await CONTEXT.close()
        if BROWSER:
            await BROWSER.close()
        CURRENT_PAGE = None
        BROWSER = None
        CONTEXT = None
        await query.edit_message_text("✅ Logged out successfully. All sessions cleared.")
        return ConversationHandler.END

async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global EMAIL
    EMAIL = update.message.text.strip()
    await update.message.reply_text("Now send me your Adsterra password:")
    return PASSWORD_STATE

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PASSWORD
    PASSWORD = update.message.text.strip()
    await update.message.reply_text("🔄 Attempting to login... Please wait.")
    await perform_login(update, context)
    return ConversationHandler.END

# ===================== PLAYWRIGHT ACTIONS =====================
async def perform_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_PAGE, BROWSER, CONTEXT

    async with async_playwright() as p:
        BROWSER = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )

        CONTEXT = await BROWSER.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
        )

        await CONTEXT.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        CURRENT_PAGE = await CONTEXT.new_page()
        CURRENT_PAGE.set_default_timeout(45000)

        try:
            await CURRENT_PAGE.goto("https://adsterra.com/login/", wait_until="networkidle")
            await human_delay(2, 4)

            await human_type(CURRENT_PAGE, 'input[name="email"]', EMAIL)
            await human_delay(1, 2)
            await human_type(CURRENT_PAGE, 'input[name="password"]', PASSWORD)
            await human_delay(1.5, 3)

            await CURRENT_PAGE.click('button[type="submit"]')
            await CURRENT_PAGE.wait_for_load_state("networkidle")
            await human_delay(4, 6)

            if "dashboard" in CURRENT_PAGE.url.lower() or await CURRENT_PAGE.locator("text=Dashboard").count() > 0:
                await update.message.reply_text("✅ Login successful! You can now create Smartlinks.")
                await send_message(context, f"✅ User {EMAIL} logged in at {datetime.now().strftime('%H:%M:%S')}")
            else:
                await update.message.reply_text("⚠️ Login failed or 2FA required. Try again.")
        except Exception as e:
            await update.message.reply_text(f"❌ Login error: {str(e)}")

async def create_smartlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not CURRENT_PAGE:
        await update.message.reply_text("No active session. Please login first.")
        return

    try:
        await update.message.reply_text("📍 Navigating to Smartlinks...")
        await CURRENT_PAGE.goto("https://adsterra.com/publishers/smartlinks/", wait_until="networkidle")
        await human_delay(3, 5.5)

        await update.message.reply_text("🆕 Creating new Smartlink...")
        await CURRENT_PAGE.click("text=Create Smartlink")
        await human_delay(2.5, 4.5)

        smartlink_name = f"Auto_Link_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        await human_type(CURRENT_PAGE, 'input[name="name"]', smartlink_name)
        await human_delay(1, 2)

        await CURRENT_PAGE.select_option('select[name="category"]', index=1)
        await human_delay(1.5, 3)

        await CURRENT_PAGE.click("text=Create")
        await human_delay(5, 8)

        smartlink_url = None
        try:
            url_input = await CURRENT_PAGE.wait_for_selector("input[value^='https://']", timeout=15000)
            if url_input:
                smartlink_url = await url_input.input_value()
                await update.message.reply_text(
                    f"🎉 Smartlink Created!\n\nName: {smartlink_name}\n🔗 {smartlink_url}"
                )
                await send_message(context, f"New Smartlink: {smartlink_url}")
        except Exception:
            await update.message.reply_text(
                "Smartlink created but URL could not be extracted automatically. Check your dashboard."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error creating smartlink: {str(e)}")

# ===================== MAIN =====================
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            EMAIL_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)],
            PASSWORD_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Adsterra Telegram Bot is running... Send /start to begin.")
    app.run_polling()

if __name__ == "__main__":
    main()
