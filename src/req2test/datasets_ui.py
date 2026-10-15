"""Minimal data upload flow using the existing authenticated task API."""


def render_datasets_html():
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据驱动测试 · Req2Test</title><style>body{font:16px system-ui;max-width:960px;margin:32px auto;padding:0 20px;color:#243348}label{display:block;margin:16px 0 6px}textarea,input[type=text]{box-sizing:border-box;width:100%;padding:10px}button{padding:10px;margin:16px 12px 0 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px}</style>
<nav><a href="/workbench">工作台</a> · <a href="/contracts">OpenAPI 导入</a> · <a href="/tasks">任务</a></nav>
<h1>数据驱动接口测试</h1><p>为同一个接口上传多组 JSON 或 CSV 数据。上传与预览不会访问目标，执行会真实发送请求，请使用已授权测试环境。</p>
<label for="base">目标地址</label><input id="base" type="text" placeholder="http://127.0.0.1:8081">
<label for="template">接口模板（JSON；数据行覆盖相应字段）</label><textarea id="template" rows="8" spellcheck="false">{"case_id":"LOGIN","name":"登录接口","method":"POST","path":"/login","expected_status":200}</textarea>
<label for="file">测试数据（JSON 数组或 CSV，1 MiB / 20 行以内）</label><input id="file" type="file" accept=".json,.csv">
<p>每行必须有唯一 id，可提供 json_body、query、headers、expected_status、assertions 等字段。CSV 中这些结构化单元格使用 JSON；空单元格继承模板。</p>
<label><input id="http" type="checkbox" checked>HTTP Tool</label><label><input id="pytest" type="checkbox" checked>Pytest Runner</label>
<p>双工具模式下，含写请求的集合只发送一轮请求，Pytest 复核该轮记录；纯读取集合分别执行。仅选 Pytest 时独立发送请求。</p>
<label><input id="isolation" type="checkbox">使用本地 Mock 数据隔离（需服务端开启，接口为 /isolated/products）</label>
<label for="seed">Mock 前置商品数据（可选 JSON 数组）</label><textarea id="seed" rows="2">[]</textarea>
<button id="preview">预览测试规格</button><button id="execute" disabled>创建并执行任务</button>
<p id="status" role="status" aria-live="polite"></p><pre id="output"></pre>
<script>
const el=id=>document.getElementById(id);let previewed=null;
function invalidate(){previewed=null;el('execute').disabled=true;}
for(const id of ['base','template','file','http','pytest','isolation','seed'])el(id).addEventListener('input',invalidate);
async function plan(){const file=el('file').files[0];if(!file||file.size>1048576)throw new Error('请选择不超过 1 MiB 的 JSON 或 CSV 数据文件');let binary='';for(const byte of new Uint8Array(await file.arrayBuffer()))binary+=String.fromCharCode(byte);return {base_url:el('base').value,template:JSON.parse(el('template').value),dataset:{filename:file.name,content_base64:btoa(binary)},run_http_tool:el('http').checked,run_pytest:el('pytest').checked,mock_isolation:el('isolation').checked,mock_seed:JSON.parse(el('seed').value)};}
async function api(path,body){const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'输入未通过校验，请检查数据格式和登录状态');return data;}
async function action(fn){try{el('status').textContent='处理中…';await fn();}catch(e){el('status').textContent=e instanceof SyntaxError?'接口模板或前置数据不是合法 JSON':e.message;}}
el('preview').onclick=()=>action(async()=>{invalidate();const input=await plan(),result=await api('/api/v1/datasets/preview',input);el('output').textContent=JSON.stringify(result,null,2);previewed=JSON.stringify(input);el('execute').disabled=false;el('status').textContent='已预览 '+result.api_specs.length+' 组数据，敏感字段已脱敏。尚未访问目标。';});
el('execute').onclick=()=>action(async()=>{const input=await plan();if(JSON.stringify(input)!==previewed)throw new Error('配置已改变，请重新预览');el('execute').disabled=true;const result=await api('/api/v1/tasks',{title:'数据驱动接口测试',requirement_text:'执行用户提供的接口数据集',data_driven:input});location.href='/tasks/'+encodeURIComponent(result.task_id);});
</script></html>"""
