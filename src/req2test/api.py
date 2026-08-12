"""FastAPI service for asynchronous Req2Test task submission and progress streaming."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import GenerationConfig, LLMSettings
from .task_store import task_store
from .worker import generate_test_cases

app = FastAPI(title="Req2Test Agent API", version="0.2.0")


class TaskCreateRequest(BaseModel):
    requirement_text: str = Field(min_length=1)
    llm_settings: LLMSettings = Field(default_factory=LLMSettings)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "task_store": task_store.backend}


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    """Small zero-build demo page that shows WebSocket task progress in real time."""
    return """
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Req2Test Async Demo</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;background:#f6f7f9;color:#202124}
.card{background:white;border-radius:14px;padding:24px;box-shadow:0 4px 18px rgba(0,0,0,.06);margin-bottom:18px}
textarea{width:100%;height:180px;box-sizing:border-box;padding:12px;border:1px solid #d0d5dd;border-radius:8px}
button{margin-top:12px;padding:10px 18px;border:0;border-radius:8px;background:#111827;color:#fff;cursor:pointer}
progress{width:100%;height:20px}.meta{font-size:14px;color:#667085}.result{white-space:pre-wrap;max-height:360px;overflow:auto;background:#f9fafb;padding:12px;border-radius:8px}
</style>
</head>
<body>
<div class="card"><h1>Req2Test Agent · 异步任务演示</h1><p class="meta">FastAPI + RabbitMQ/Celery + Redis + WebSocket + LangGraph</p>
<textarea id="req">用户可以新增供应商，填写供应商名称、联系人和联系电话后保存。保存成功后供应商出现在列表中。</textarea>
<button onclick="submitTask()">提交异步任务</button></div>
<div class="card"><div id="status">等待提交</div><progress id="progress" max="100" value="0"></progress><p id="message" class="meta"></p><div id="result" class="result"></div></div>
<script>
async function submitTask(){
  const requirement_text=document.getElementById('req').value;
  const resp=await fetch('/api/v1/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({requirement_text})});
  const data=await resp.json();
  if(!resp.ok){document.getElementById('status').textContent='提交失败';document.getElementById('message').textContent=JSON.stringify(data);return;}
  document.getElementById('status').textContent='Task ID: '+data.task_id;
  const scheme=location.protocol==='https:'?'wss':'ws';
  const ws=new WebSocket(`${scheme}://${location.host}${data.ws_url}`);
  ws.onmessage=(event)=>{
    const state=JSON.parse(event.data);
    document.getElementById('progress').value=state.progress||0;
    document.getElementById('message').textContent=`${state.stage||''} · ${state.message||''}`;
    if(state.result){document.getElementById('result').textContent=JSON.stringify(state.result,null,2);}
    if(state.error){document.getElementById('result').textContent=state.error;}
  };
}
</script>
</body></html>
"""


@app.post("/api/v1/tasks", status_code=202)
def create_task(request: TaskCreateRequest) -> dict[str, str]:
    task_id = str(uuid4())
    task_store.create(task_id, payload={"source": "api"})

    eager = os.getenv("REQ2TEST_EAGER_TASKS", "false").lower() in {"1", "true", "yes"}
    if eager:
        generate_test_cases.apply(
            args=[
                task_id,
                request.requirement_text,
                request.llm_settings.model_dump(),
                request.generation_config.model_dump(),
            ]
        )
    else:
        async_result = generate_test_cases.delay(
            task_id,
            request.requirement_text,
            request.llm_settings.model_dump(),
            request.generation_config.model_dump(),
        )
        task_store.update(task_id, celery_task_id=async_result.id)

    return {"task_id": task_id, "status_url": f"/api/v1/tasks/{task_id}", "ws_url": f"/ws/tasks/{task_id}"}


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str):
    state = task_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return state


@app.websocket("/ws/tasks/{task_id}")
async def task_progress(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    last_updated = None
    try:
        while True:
            state = task_store.get(task_id)
            if state is None:
                await websocket.send_json({"task_id": task_id, "status": "missing"})
                return
            if state.get("updated_at") != last_updated:
                await websocket.send_json(state)
                last_updated = state.get("updated_at")
            if state.get("status") in {"completed", "failed"}:
                return
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
