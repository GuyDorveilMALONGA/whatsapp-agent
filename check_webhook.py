import asyncio
from dotenv import load_dotenv
load_dotenv()
from services.telegram import get_webhook_info

result = asyncio.run(get_webhook_info())
print(result)