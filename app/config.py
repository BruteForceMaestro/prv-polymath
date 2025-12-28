import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelInfo


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "oopsie")
POLYMATH_API_KEY = os.getenv("POLYMATH_API_KEY", 'oops')
MODEL_RESEARCHER = "gpt-5.2" # when actually testing performance set to gpt-5.2
MODEL_BUDGET = "gpt-5-mini" # nano turns out to be too stupid
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
    model_info=gpt5_info,
    timeout=600
)

budget_model_client = OpenAIChatCompletionClient(
    model=MODEL_BUDGET,
    api_key=OPENAI_API_KEY,
    model_info=gpt5_info,
    timeout=600
)

semaphore = None

def get_limiter():
    global semaphore
    if semaphore is None:
        semaphore = asyncio.Semaphore(10)
    return semaphore