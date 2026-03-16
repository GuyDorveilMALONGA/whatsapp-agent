"""
set_webhook.py — enregistre le webhook Telegram avec secret_token.
"""
import asyncio
import os
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from dotenv import load_dotenv
load_dotenv()

from services.telegram import set_webhook

async def main():
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    url    = "https://web-production-ccab8.up.railway.app"

    print(f"URL      : {url}/telegram/webhook")
    print(f"Secret   : {'✅ défini (' + secret[:4] + '...)' if secret else '❌ ABSENT — webhook non sécurisé'}")
    print()

    ok = await set_webhook(url, secret_token=secret)
    if ok:
        print("✅ Webhook Telegram enregistré avec succès !")
    else:
        print("❌ Échec — vérifie TELEGRAM_BOT_TOKEN dans ton .env")

asyncio.run(main())