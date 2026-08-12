"""FastAPI service for asynchronous Req2Test generation, tool execution and progress streaming."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import GenerationConfig, LLMSettings
from .execution_models import ExecutionConfig
from .task_store import task_store
from .worker import generate_test_cases

app = FastAPI(title="Req2Test Agent API", version="0.3.0")


class TaskCreateRequest(BaseModel):
    requirement_text: str = Field(min_length=1)
    llm_settings: LLMSettings = Field(default_factory=LLMSettings)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)
    execution_config: ExecutionConfig = Field(default_factory=ExecutionConfig)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "task_store": task_store.backend}


# Small deterministic endpoints used only to demonstrate the HTTP/Pytest execution
# layer without requiring the user to prepare another test service.
@app.get("/demo-target/health")
def demo_target_health() -> dict[str, str]:
    return {"status": "ok", "service": "req2test-demo-target"}


@app.post("/demo-target/echo")
def demo_target_echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "received": payload}


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    """Zero-build demo page showing generation and optional real test execution."""
    return """
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Req2Test Async Demo</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;max-width:960px;margin:40px auto;padding:0 20px;background:#f6f7f9;color:#202124}
.card{background:white;border-radius:14px;padding:24px;box-shadow:0 4px 18px rgba(0,0,0,.06);margin-bottom:18px}
textarea,input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #d0d5dd;border-radius:8px} textarea{height:220px}
button{margin-top:12px;padding:10px 18px;border:0;border-radius:8px;background:#111827;color:#fff;cursor:pointer}
progress{width:100%;height:20px}.meta{font-size:14px;color:#667085}.result{white-space:pre-wrap;max-height:520px;overflow:auto;background:#f9fafb;padding:12px;border-radius:8px}
.row{display:flex;gap:12px;align-items:center;margin-top:12px}.row input[type=checkbox]{width:auto}.row label{font-size:14px}.hint{font-size:12px;color:#667085}
</style>
</head>
<body>
<div class="card">
<h1>Req2Test Agent · AI 测试执行演示</h1>
<p class="meta">FastAPI + RabbitMQ/Celery + Redis + WebSocket + LangGraph + Chroma RAG + HTTP Tool + Pytest</p>
<textarea id="req"># 供应商管理
用户可以新增供应商，填写供应商名称、联系人和联系电话后保存。

# 可执行接口契约
GET /demo-target/health 状态码: 200 响应包含: {"status":"ok"}</textarea>
<div class="row"><input id="execute" type="checkbox"/><label for="execute">生成后执行 HTTP Tool + Pytest</label></div>
<label class="meta" for="baseUrl">被测服务 Base URL</label>
<input id="baseUrl" placeholder="http://localhost:8000" />
<p class="hint">本机启动可填 http://localhost:8000；Docker Compose 中 Worker 访问本项目演示接口时可填 http://api:8000。</p>
<button onclick="submitTask()">提交异步任务</button>
</div>
<div class="card"><div id="status">等待提交</div><progress id="progress" max="100" value="0"></progress><p id="message" class="meta"></p><div id="result" class="result"></div></div>
<script>
document.getElementById('baseUrl').value=location.origin;
async function submitTask(){
  const requirement_text=document.getElementById('req').value;
  const enabled=document.getElementById('execute').checked;
  const base_url=document.getElementById('baseUrl').value.trim();
  const resp=await fetch('/api/v1/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    requirement_text,
    execution_config:{enabled,base_url,run_http_tool:true,run_pytest:true}
  })});
  const data=await resp.json();
  if(!resp.ok){document.getElementById('status').textContent='提交失败';document.getElementById('message').textContent=JSON.stringify(data);return;}
  document.getElementById('status').textContent='Task ID: '+data.task_id;
  document.getElementById('result').textContent='';
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
    task_store.create(
        task_id,
        payload={
            "source": "api",
            "execution_enabled": request.execution_config.enabled,
        },
    )

    task_args = [
        task_id,
        request.requirement_text,
        request.llm_settings.model_dump(),
        request.generation_config.model_dump(),
        request.execution_config.model_dump(),
    ]
    eager = os.getenv("REQ2TEST_EAGER_TASKS", "false").lower() in {"1", "true", "yes"}
    if eager:
        generate_test_cases.apply(args=task_args)
    else:
        async_result = generate_test_cases.delay(*task_args)
        task_store.update(task_id, celery_task_id=async_result.id)

    return {
        "task_id": task_id,
        "status_url": f"/api/v1/tasks/{task_id}",
        "ws_url": f"/ws/tasks/{task_id}",
    }


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
