from tina import Agent,Tools
from tina.MCP import MCPClient
from tina.LLM import BaseAPI
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket
from typing import Optional
import asyncio
import json
import os
import sys
import uvicorn

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/src", StaticFiles(directory="src"), name="src")
llm = None
@app.get("/", response_class=HTMLResponse)
async def get():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        return open("static/index.html").read()
    else:
        return open("static/welcome.html").read()

@app.post("/configllm")
async def set_config_llm(request: Request):
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    config = await request.json()
    api_key = config.get("api_key")
    if not api_key:
        return {"error": "api_key is required"}
    model_name = config.get("model_name")
    if not model_name:
        return {"error": "model_name is required"}
    base_url = config.get("base_url")
    if not base_url:
        return {"error": "base_url is required"}
    max_input = config.get("max_input")
    if not max_input:
        return {"error": "max_input is required"}
    with open(env_path, "w") as f:
        f.write(f"LLM_API_KEY={api_key}\n")
        f.write(f"MODEL_NAME={model_name}\n")
        f.write(f"BASE_URL={base_url}\n")
        f.write(f"MAX_INPUT={max_input}\n")
    llm = BaseAPI()
    return {"success": "成功设置了LLM配置"}    

