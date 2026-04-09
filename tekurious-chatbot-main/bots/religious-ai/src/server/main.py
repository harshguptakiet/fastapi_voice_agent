import os
import re
import logging
import traceback
import uuid
from typing import Any
import json
import uvicorn
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, File, UploadFile, Form
from langchain.output_parsers import PydanticOutputParser
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
#from llm.gemini import get_gemini_engine

from llm.dynamic_llm import get_llm_engine

from fastapi.responses import JSONResponse
from intent_guard import is_religious_topic_allowed_by_intent, RELIGIOUS_FALLBACK
from pathlib import Path
from llm.output_parser import ParseOutput
from llm.input import ParseInput
from utils.common import DHOME
from guardrails.guardrails import Guardrails


def _load_env():
    base_dir = Path(__file__).resolve().parents[1]
    load_dotenv(base_dir / ".env", override=False)


_load_env()

#For speech-to-speech POC
try:
    # Optional dependency chain (Azure Speech + Azure OpenAI). Keep the service
    # runnable even if these packages aren't installed.
    from server.s2s import run_s2s  # type: ignore
except Exception:
    run_s2s = None
import threading

malicious_pattern = re.compile(r"\$\(\s*(\w+)\s*.*?\)")

def is_malicious(data: Any) -> bool:
    """
    Recursively checks if the given data contains malicious patterns.

    Args:
        data (Any): The data to check, which can be a dictionary, list, or string.

    Returns:
        bool: True if malicious patterns are detected, False otherwise.
    """
    if isinstance(data, dict):
        return any(is_malicious(value) for value in data.values())
    elif isinstance(data, list):
        return any(is_malicious(item) for item in data)
    elif isinstance(data, str):
        return bool(malicious_pattern.search(data))
    return False

def validate_data(data_dict, request_type):
    
    if request_type == "chat" and "query" in data_dict and data_dict["query"] in ["", None, "null"]:
        return False, "Either query is not present or its valuse is invalid."
    
    return True, "valid"

def get_llm_response(query: str) -> ParseOutput:
    llm_engine = get_llm_engine()
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "analyze_query.yaml"
    llm_engine.prompt = llm_engine.load_prompt(prompt_path)
    
    if not llm_engine.prompt:
        raise ValueError(f"Prompt couldn't be assigned to {llm_engine.provider} engine. Please load the prompt and initialize the chain.")

    llm_engine.set_output_parser(PydanticOutputParser(pydantic_object=ParseOutput))
    llm_engine.get_llm_sequence(llm_engine.prompt)
    query_model = ParseInput(query=query)
    
    result = llm_engine.respond(query_model)
    
    return result
""" 
def get_llm_response(query: str ) -> ParseOutput:
    gemini_engine = get_gemini_engine()
    prompt_path = os.path.join("prompts", "analyze_query.yaml")
    print("prompt_path:", prompt_path)
    gemini_engine.prompt = gemini_engine.load_prompt(Path(prompt_path))

    if not gemini_engine.prompt:
        raise ValueError("Prompt couldn't be assigned to GeminiEngine. Please load the prompt and initialize the chain.")

    gemini_engine.set_output_parser(PydanticOutputParser(pydantic_object=ParseOutput))
    gemini_engine.get_llm_sequence(gemini_engine.prompt)
    query_model = ParseInput(query=query)
    
    result = gemini_engine.respond(query_model)

    return result
"""

app = FastAPI()

logger = logging.getLogger("uvicorn.error")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "darshan-ai",
        "endpoints": {"chat": "/chat", "docs": "/docs", "health": "/health"},
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(status_code=204, content=None)

@app.post("/chat")
async def chat(request: Request):
    start_datetime = datetime.now()
    try:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        # Support both:
        # - POST /chat?query=...
        # - POST /chat with JSON body {"query": "..."}
        data_dict = dict(request.query_params)
        if not data_dict:
            try:
                body = await request.json()
                if isinstance(body, dict) and "query" in body:
                    data_dict = {"query": body.get("query")}
            except Exception:
                pass
        
        if is_malicious(data_dict):
            print(f"Malicious payload detected: {data_dict}")
            raise HTTPException(status_code=400, detail="Malicious payload detected")

        val_status, msg = validate_data(data_dict, "chat")
        if not val_status:
            msg = "ERR-101" + ":" + msg
            print(msg)
            raise HTTPException(status_code=404, detail=msg)

        query = data_dict["query"]


        # Strict religious topic guardrail
        if not is_religious_topic_allowed_by_intent(query):
            return {"response": RELIGIOUS_FALLBACK}

        result = get_llm_response(query)
        response = result.output
        return {"response": response, "request_id": request_id}
    except HTTPException as err:
        raise err
    except (ValueError, ImportError) as e:
        err_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        logger.error("request_id=%s /chat failed: %s", request_id, err_text)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Upstream LLM error. Please try again.",
                "request_id": request_id,
            },
        )
    except Exception as e:
        err_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        logger.error("request_id=%s /chat crashed: %s", request_id, err_text)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "An internal error occurred. Please try again later.",
                "request_id": request_id,
            },
        )
#speech-to-speech POC
@app.post("/s2s")
def s2s_chat():
    if run_s2s is None:
        return JSONResponse(
            status_code=501,
            content={
                "status": "S2S is not available",
                "message": "Optional speech-to-speech dependencies are not installed.",
            },
        )

    thread = threading.Thread(target=run_s2s)
    thread.start()
    return {"status": "S2S session started in the background."}
    

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print("Starting the service on PORT:", str(port))
    reload_enabled = str(os.getenv("UVICORN_RELOAD", "1")).strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        "server.main:app", host="0.0.0.0", port=port, reload=reload_enabled
    )