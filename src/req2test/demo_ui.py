"""Browser demo page for the asynchronous AI test execution workflow."""

DEMO_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Req2Test AI Test Platform</title>
<style>
:root{color-scheme:light;--bg:#f5f7fb;--card:#fff;--text:#172033;--muted:#667085;--line:#e4e7ec;--blue:#2563eb;--green:#15803d;--red:#b42318;--amber:#b54708}
*{box-sizing:border-box}body{font-family:Inter,system-ui,-apple-system,"PingFang SC",sans-serif;max-width:1080px;margin:0 auto;padding:34px 22px 70px;background:var(--bg);color:var(--text)}
.card{background:var(--card);border:1px solid #eef0f4;border-radius:16px;padding:24px;box-shadow:0 5px 22px rgba(16,24,40,.05);margin-bottom:18px}
h1{margin:0 0 6px;font-size:26px}h2{font-size:17px;margin:0 0 14px}.meta,.hint{color:var(--muted);font-size:13px}.hint{margin:7px 0 0}
textarea,input{width:100%;padding:12px;border:1px solid #d0d5dd;border-radius:9px;background:#fff;color:var(--text)}textarea{height:210px;resize:vertical}
.actions{display:flex;gap:9px;flex-wrap:wrap;margin:12px 0}.btn{padding:9px 14px;border:0;border-radius:8px;cursor:pointer;font-weight:600}.primary{background:#111827;color:#fff}.secondary{background:#eef2ff;color:#3448a3}.danger{background:#fff1f1;color:#a31212}
.row{display:flex;gap:10px;align-items:center;margin:12px 0}.row input[type=checkbox]{width:auto}.row label{font-size:14px}progress{width:100%;height:18px;margin:10px 0}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}.metric{border:1px solid var(--line);border-radius:11px;padding:13px}.metric .value{font-size:22px;font-weight:750}.metric .label{font-size:12px;color:var(--muted);margin-top:3px}
.badge{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:12px;font-weight:700}.pass{background:#ecfdf3;color:var(--green)}.fail{background:#fef3f2;color:var(--red)}.skip{background:#fff7ed;color:var(--amber)}
.case{border:1px solid var(--line);border-radius:10px;padding:12px;margin:8px 0}.case-head{display:flex;justify-content:space-between;gap:12px}.case-title{font-weight:700}.small{font-size:12px;color:var(--muted)}
.failure{border-left:4px solid #f04438;background:#fff7f6;border-radius:8px;padding:12px;margin:9px 0}.failure strong{color:var(--red)}
details{margin-top:14px}pre{white-space:pre-wrap;word-break:break-word;background:#101828;color:#e4e7ec;border-radius:10px;padding:14px;max-height:420px;overflow:auto;font-size:12px}
#emptyExecution{color:var(--muted);font-size:13px}@media(max-width:760px){.grid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="card">
  <h1>Req2Test Agent · AI 测试执行平台</h1>
  <p class="meta">RAG + LangGraph + FastAPI + RabbitMQ/Celery + Redis + WebSocket + HTTP Tool + Pytest</p>
  <div class="actions">
    <button class="btn secondary" onclick="loadPassDemo()">载入全通过 Demo</button>
    <button class="btn danger" onclick="loadFailDemo()">载入失败归因 Demo</button>
  </div>
  <textarea id="req"></textarea>
  <div class="row"><input id="execute" type="checkbox" checked/><label for="execute">生成后执行 HTTP Tool + Pytest</label></div>
  <label class="meta" for="baseUrl">被测服务 Base URL</label>
  <input id="baseUrl" placeholder="http://localhost:8000" />
  <p class="hint">Docker Compose 中 Worker 访问本项目演示接口时填写 http://api:8000。</p>
  <button class="btn primary" onclick="submitTask()">提交异步任务</button>
</div>

<div class="card">
  <h2>任务状态</h2>
  <div id="taskId" class="meta">等待提交</div>
  <progress id="progress" max="100" value="0"></progress>
  <div id="message" class="meta"></div>
</div>

<div class="card">
  <h2>执行结果</h2>
  <div id="emptyExecution">任务完成后将在这里展示 HTTP 与 Pytest 执行摘要。</div>
  <div id="execution" style="display:none">
    <div class="grid">
      <div class="metric"><div id="totalCases" class="value">0</div><div class="label">HTTP 用例</div></div>
      <div class="metric"><div id="passedCases" class="value">0</div><div class="label">HTTP 通过</div></div>
      <div class="metric"><div id="failedCases" class="value">0</div><div class="label">HTTP 失败</div></div>
      <div class="metric"><div id="pytestState" class="value">-</div><div class="label">Pytest</div></div>
    </div>
    <div id="caseList"></div>
    <div id="failureList"></div>
  </div>
  <details><summary>查看原始 JSON</summary><pre id="rawResult">暂无结果</pre></details>
</div>

<script>
const PASS_DEMO=`# 可执行接口契约
GET /demo-target/health
预期状态码：200
响应包含：{"status":"ok"}

POST /demo-target/echo
请求体：{"message":"hello"}
预期状态码：200
响应包含：{"status":"ok"}`;
const FAIL_DEMO=`# 可执行接口契约
GET /demo-target/health
预期状态码：200
响应包含：{"status":"ok"}

POST /demo-target/echo
预期状态码：200`;
function loadPassDemo(){document.getElementById('req').value=PASS_DEMO}
function loadFailDemo(){document.getElementById('req').value=FAIL_DEMO}
loadPassDemo();
document.getElementById('baseUrl').value='http://api:8000';

function badge(ok){return `<span class="badge ${ok?'pass':'fail'}">${ok?'PASS':'FAIL'}</span>`}
function renderExecution(result){
  document.getElementById('rawResult').textContent=JSON.stringify(result,null,2);
  const execution=result && result.execution;
  if(!execution){return}
  const summary=execution.summary||{};
  document.getElementById('emptyExecution').style.display='none';
  document.getElementById('execution').style.display='block';
  document.getElementById('totalCases').textContent=summary.total_http_cases??(execution.http_results||[]).length;
  document.getElementById('passedCases').textContent=summary.passed_http_cases??0;
  document.getElementById('failedCases').textContent=summary.failed_http_cases??0;
  const pytestPassed=summary.pytest_passed;
  document.getElementById('pytestState').innerHTML=pytestPassed===true?'<span class="badge pass">PASS</span>':pytestPassed===false?'<span class="badge fail">FAIL</span>':'<span class="badge skip">SKIP</span>';

  const cases=execution.http_results||[];
  document.getElementById('caseList').innerHTML=cases.map(item=>`<div class="case"><div class="case-head"><div><div class="case-title">${item.method} ${new URL(item.url).pathname}</div><div class="small">${item.case_id} · ${item.duration_ms??'-'} ms · expected ${item.expected_status} / actual ${item.status_code??'-'}</div></div>${badge(item.passed)}</div>${item.failures&&item.failures.length?`<div class="small" style="margin-top:8px">${item.failures.join('；')}</div>`:''}</div>`).join('');

  const failures=execution.failure_analysis||[];
  document.getElementById('failureList').innerHTML=failures.length?`<h2 style="margin-top:18px">失败归因</h2>`+failures.map(item=>`<div class="failure"><strong>${item.case_id} · ${item.category}</strong><div>${item.probable_cause}</div><div class="small" style="margin-top:6px">证据：${(item.evidence||[]).join('；')}</div><div class="small">建议：${item.suggestion||'-'}</div></div>`).join(''):'';
}

async function submitTask(){
  const requirement_text=document.getElementById('req').value;
  const enabled=document.getElementById('execute').checked;
  const base_url=document.getElementById('baseUrl').value.trim();
  document.getElementById('execution').style.display='none';
  document.getElementById('emptyExecution').style.display='block';
  document.getElementById('rawResult').textContent='任务执行中...';
  const resp=await fetch('/api/v1/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({requirement_text,execution_config:{enabled,base_url,run_http_tool:true,run_pytest:true}})});
  const data=await resp.json();
  if(!resp.ok){document.getElementById('taskId').textContent='提交失败';document.getElementById('message').textContent=JSON.stringify(data);return}
  document.getElementById('taskId').textContent='Task ID: '+data.task_id;
  const scheme=location.protocol==='https:'?'wss':'ws';
  const ws=new WebSocket(`${scheme}://${location.host}${data.ws_url}`);
  ws.onmessage=(event)=>{
    const state=JSON.parse(event.data);
    document.getElementById('progress').value=state.progress||0;
    document.getElementById('message').textContent=`${state.stage||''} · ${state.message||''}`;
    if(state.result){renderExecution(state.result)}
    if(state.error){document.getElementById('rawResult').textContent=state.error}
  };
}
</script>
</body></html>
"""
