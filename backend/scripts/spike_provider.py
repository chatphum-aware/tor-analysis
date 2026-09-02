"""Provider capability spike. Proves a vendor SDK can (a) constrain output to
one of our real group schemas and (b) report token usage, BEFORE an adapter is
written against a remembered API shape.

Usage (from the backend/ directory):
    OPENAI_API_KEY=... python scripts/spike_provider.py openai gpt-<model>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Run as a plain script (not `python -m`), so app/ isn't on sys.path by
# default -- add backend/ (this script's parent directory) explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schema import BasicInfoGroup  # noqa: E402

DOC = """[หน้า 1]
ประกาศกรมสรรพากร
เรื่อง ประกวดราคาจ้างพนักงานรักษาความสะอาด ประจำปีงบประมาณ พ.ศ. 2569
ราคากลางของงานจ้าง เป็นเงินทั้งสิ้น 7,672,800.00 บาท
"""


def spike_openai(model: str) -> None:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    print("--- dir(client.chat.completions) ---")
    print([n for n in dir(client.chat.completions) if not n.startswith("_")])

    completion = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "Extract per the schema. Cite page and quote."},
            {"role": "user", "content": DOC},
        ],
        response_format=BasicInfoGroup,
    )
    print("--- parsed ---")
    print(completion.choices[0].message.parsed)
    print("--- usage repr (note the exact field names) ---")
    print(repr(completion.usage))
    print(json.dumps(completion.usage.model_dump(), indent=2, ensure_ascii=False))


def spike_gemini(model: str) -> None:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    print("--- dir(client.models) ---")
    print([n for n in dir(client.models) if not n.startswith("_")])

    response = client.models.generate_content(
        model=model,
        contents=DOC,
        config={
            "response_mime_type": "application/json",
            "response_schema": BasicInfoGroup,
            "system_instruction": "Extract per the schema. Cite page and quote.",
        },
    )
    print("--- .parsed ---")
    print(response.parsed)
    print("--- usage_metadata repr (note exact field names) ---")
    print(repr(response.usage_metadata))


if __name__ == "__main__":
    provider, model = sys.argv[1], sys.argv[2]
    {"openai": spike_openai, "gemini": spike_gemini}[provider](model)
