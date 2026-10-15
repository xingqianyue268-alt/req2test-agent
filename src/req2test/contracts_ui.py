"""Small contract import screen; execution uses the existing task pipeline."""


def render_contracts_html():
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>接口契约 · Req2Test</title>
<style>body{font:16px system-ui;color:#243348;background:#f4f6f8;max-width:1000px;margin:32px auto;padding:0 20px}main{background:white;padding:24px;border-radius:12px}label{display:block;margin:16px 0 6px}input[type=text],textarea{box-sizing:border-box;width:100%;padding:10px;border:1px solid #adb9c9;border-radius:5px}button{padding:10px 16px;margin:12px 8px 12px 0;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px}small{color:#526477}#operations label{border-bottom:1px solid #eee;padding:8px}</style>
<nav><a href="/workbench">工作台</a> · <a href="/tasks">测试任务</a> · <a href="/datasets">数据驱动测试</a></nav>
<h1>OpenAPI 接口测试</h1><main>
<p>上传只解析文件。选择接口、配置已授权目标并预览后，再主动执行。测试可能写入目标数据，请使用测试环境。</p>
<label for="file">OpenAPI 3.0 / 3.1 JSON 或 YAML（最多 1 MiB）</label>
<input id="file" type="file" accept=".json,.yaml,.yml"><button id="import">解析文件</button>
<div id="operations"></div>
<label for="base">目标环境地址</label><input id="base" type="text" placeholder="http://127.0.0.1:8081">
<label for="headers">测试认证及公共请求头（JSON，不会保存到浏览器）</label><textarea id="headers" rows="3" spellcheck="false">{}</textarea>
<label for="overrides">接口数据覆盖（可选，按「POST /products」等接口标识填写）</label>
<textarea id="overrides" rows="4" spellcheck="false">{}</textarea>
<small>支持 path、query、headers、json_body、expected_status、expected_json_contains。例如 {"GET /users/{id}": {"path": {"id": 1}}}。样例仅为起点，不保证目标业务接受。</small>
<label><input id="validation" type="checkbox" checked>生成缺失字段、类型错误等校验用例（契约需声明 400 / 422）</label>
<label><input id="http" type="checkbox" checked>HTTP Tool</label><label><input id="pytest" type="checkbox" checked>Pytest Runner</label>
<p><small>双执行器模式下，含写请求的集合只发送一轮请求，Pytest 复核该轮记录；纯读取集合仍分别执行。</small></p>
<button id="preview">预览测试规格</button><button id="execute" disabled>创建并执行任务</button>
<p id="status" role="status" aria-live="polite"></p><pre id="output"></pre></main>
<script>
const el=id=>document.getElementById(id);let upload=null,previewed=null;
async function api(url,body){const r=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'请求未通过校验，请检查输入或登录状态');return data;}
function invalidate(){previewed=null;el('execute').disabled=true;}
function plan(){if(!upload)throw new Error('请先解析文件');return {...upload,selected_operations:[...document.querySelectorAll('#operations input:checked')].map(x=>x.value),base_url:el('base').value,headers:JSON.parse(el('headers').value),overrides:JSON.parse(el('overrides').value),include_validation:el('validation').checked,run_http_tool:el('http').checked,run_pytest:el('pytest').checked};}
async function action(fn){try{el('status').textContent='处理中…';await fn();}catch(e){el('status').textContent=e instanceof SyntaxError?'请求头或覆盖值不是有效 JSON':e.message;}}
for(const id of ['file','base','headers','overrides','validation','http','pytest'])el(id).addEventListener('input',invalidate);
el('import').onclick=()=>action(async()=>{invalidate();upload=null;el('operations').replaceChildren();const file=el('file').files[0];if(!file||file.size>1048576)throw new Error('请选择不超过 1 MiB 的契约文件');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(const b of bytes)binary+=String.fromCharCode(b);const input={filename:file.name,content_base64:btoa(binary)};const result=await api('/api/v1/contracts/import',input);upload=input;for(const op of result.operations){const row=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.value=op.key;box.disabled=!op.supported;box.onchange=invalidate;row.append(box,document.createTextNode(op.key+' '+(op.summary||'')+(op.supported?'':' · '+op.issues.join('；'))));el('operations').append(row);}el('output').textContent=JSON.stringify(result,null,2);el('status').textContent='解析完成。尚未访问目标，请选择接口。';});
el('preview').onclick=()=>action(async()=>{invalidate();const input=plan(),result=await api('/api/v1/contracts/preview',input);el('output').textContent=JSON.stringify(result,null,2);previewed=JSON.stringify(input);el('execute').disabled=false;el('status').textContent='规格已预览，敏感字段已脱敏。确认后可创建任务。';});
el('execute').onclick=()=>action(async()=>{const input=plan();if(JSON.stringify(input)!==previewed)throw new Error('配置已改变，请重新预览');el('execute').disabled=true;const result=await api('/api/v1/tasks',{title:'OpenAPI 接口测试',requirement_text:'执行用户选择的 OpenAPI 接口契约测试',openapi_contract:input});location.href='/tasks/'+encodeURIComponent(result.task_id);});
</script></html>"""
