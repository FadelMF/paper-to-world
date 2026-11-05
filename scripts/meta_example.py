"""Run the supplied Meta Responses example using the OpenAI Python SDK."""

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

with OpenAI(base_url="https://api.meta.ai/v1", api_key=os.getenv("LLM_API_KEY") or os.environ["MODEL_API_KEY"]) as client:
    response = client.responses.create(
        model="muse-wonder-1.0",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Write a script that randomly generates a haiku about Meta, and explain your reasoning behind what script language you would choose.",
                    }
                ],
            }
        ],
        stream=False,
    )
    print(response.model_dump_json(indent=2))
