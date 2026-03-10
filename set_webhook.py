import asyncio
from dotenv import load_dotenv
load_dotenv()
from services.telegram import set_webhook

asyncio.run(set_webhook("https://web-production-ccab8.up.railway.app"))