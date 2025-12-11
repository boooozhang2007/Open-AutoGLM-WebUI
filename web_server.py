import os
import io
import time
import base64
import json
import threading
import asyncio
from dataclasses import asdict

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

from phone_agent import PhoneAgent
from phone_agent.adb.screenshot import get_screenshot
from phone_agent.adb.connection import ADBConnection, list_devices
from phone_agent.adb.scanner import scan_network
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

# Load environment variables
load_dotenv()

app = FastAPI()

# Create templates directory if it doesn't exist
if not os.path.exists("templates"):
    os.makedirs("templates")

templates = Jinja2Templates(directory="templates")
adb_connection = ADBConnection()

# Global agent state
agent_lock = threading.Lock()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Reload env vars to pick up changes in .env without restarting
    load_dotenv(override=True)
    
    api_key = os.getenv("API_KEY", "")
    print(f"DEBUG: Reloaded .env. API_KEY found: {'Yes' if api_key else 'No'}")
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "default_model": os.getenv("MODEL_NAME", "ZhipuAI/AutoGLM-Phone-9B"),
        "default_base_url": os.getenv("BASE_URL", "https://api-inference.modelscope.cn/v1"),
        "default_api_key": api_key,
        "default_max_steps": os.getenv("MAX_STEPS", "20")
    })

@app.get("/api/scan")
def scan_devices():
    """Scan for devices on the local network."""
    ips = scan_network()
    return {"ips": ips}

@app.get("/api/devices")
def get_devices():
    devices = list_devices()
    return [{"id": d.device_id, "status": d.status, "model": d.model, "connection_type": d.connection_type.value} for d in devices]

@app.post("/api/connect")
def connect_device(address: str = Query(...)):
    success, message = adb_connection.connect(address)
    return {"success": success, "message": message}

@app.post("/api/disconnect")
def disconnect_device(address: str = Query(None)):
    success, message = adb_connection.disconnect(address)
    return {"success": success, "message": message}

@app.get("/stream")
async def stream(device_id: str = Query(None)):
    def iterfile():
        while True:
            try:
                screenshot = get_screenshot(device_id)
                
                # Decode base64 to bytes
                img_data = base64.b64decode(screenshot.base64_data)
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/png\r\n\r\n' + img_data + b'\r\n')
                # Limit FPS to avoid overloading ADB
                time.sleep(0.2) 
            except Exception as e:
                print(f"Stream error: {e}")
                time.sleep(1)
                
    return StreamingResponse(iterfile(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            task = data.get("task")
            device_id = data.get("device_id")
            
            # Config
            model_config = ModelConfig(
                base_url=data.get("base_url", "https://api-inference.modelscope.cn/v1"),
                api_key=data.get("api_key", "ms-3dd3f247-aa7d-4586-b2bf-acee47e2d213"),
                model_name=data.get("model", "ZhipuAI/AutoGLM-Phone-9B"),
            )
            
            agent_config = AgentConfig(
                max_steps=int(data.get("max_steps", 100)),
                device_id=device_id,
                verbose=True
            )
            
            agent = PhoneAgent(model_config, agent_config)
            
            # Run agent step by step
            try:
                # Initial step
                await websocket.send_json({"type": "info", "message": "Starting task..."})
                
                # Run in a separate thread to avoid blocking the event loop
                # But we need to yield results. 
                # Since agent.step is synchronous, we can run it in a thread executor
                
                loop = asyncio.get_event_loop()
                
                # First step
                result = await loop.run_in_executor(None, lambda: agent.step(task))
                await websocket.send_json({"type": "step", "data": asdict(result)})
                
                while not result.finished:
                    result = await loop.run_in_executor(None, lambda: agent.step())
                    await websocket.send_json({"type": "step", "data": asdict(result)})
                
                await websocket.send_json({"type": "finish", "message": result.message or "Task completed"})
                
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})
                traceback.print_exc()
                
    except WebSocketDisconnect:
        print("Client disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
