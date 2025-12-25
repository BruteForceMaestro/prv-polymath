import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelInfo


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "oopsie")
POLYMATH_API_KEY = os.getenv("POLYMATH_API_KEY", 'oops')
MODEL_RESEARCHER = "gpt-5.2"
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

POLYMATH_SERVER_URL = "http://localhost:8000"
if ENVIRONMENT == "prod":
    # would change POLYMATH_SERVER_URL here, but
    raise NotImplementedError("Is this thing hosted?")

client = AsyncOpenAI()
gpt5_info = ModelInfo(
    vision=True,
    function_calling=True,
    json_output=True,
    family="gpt",
    structured_output=True
)
model_client = OpenAIChatCompletionClient(
    model=MODEL_RESEARCHER,
    api_key=OPENAI_API_KEY,
    model_info=gpt5_info
)

semaphore = None

def get_limiter():
    global semaphore
    if semaphore is None:
        semaphore = asyncio.Semaphore(10)
    return semaphore