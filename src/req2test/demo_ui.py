"""Unified browser workbench for Req2Test Agent."""

DEMO_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Req2Test Agent · AI 测试工作台</title>
<style>
:root{
  color-scheme:light;
  --bg:#f5f7fb;--surface:#ffffff;--surface-2:#f8faff;--text:#172033;--muted:#667085;
  --line:#e5e9f2;--line-strong:#d8deea;--primary:#5b5ce2;--primary-2:#7c3aed;
  --primary-soft:#eef0ff;--blue:#2563eb;--green:#15803d;--green-soft:#ecfdf3;
  --red:#b42318;--red-soft:#fef3f2;--amber:#b54708;--amber-soft:#fff7ed;
  --shadow:0 10px 30px rgba(23,32,51,.06);--radius:18px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:14px}
button,input,textarea,select{font:inherit}
button{cursor:pointer}
a{color:inherit;text-decoration:none}
.shell{min-height:100vh}
.sidebar{position:fixed;inset:0 auto 0 0;width:244px;background:rgba(255,255,255,.96);border-right:1px solid var(--line);padding:22px 16px;display:flex;flex-direction:column;z-index:20;backdrop-filter:blur(18px)}
.brand{display:flex;align-items:center;gap:11px;padding:2px 8px 24px}.brand-mark{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,var(--primary),var(--primary-2));display:grid;place-items:center;color:#fff;font-weight:800;box-shadow:0 8px 18px rgba(91,92,226,.24)}
.brand-title{font-weight:800;font-size:16px;letter-spacing:-.02em}.brand-sub{font-size:11px;color:var(--muted);margin-top:2px}
.nav-label{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#98a2b3;font-weight:700;padding:0 10px 8px}.nav{display:grid;gap:5px}.nav a{display:flex;align-items:center;gap:10px;padding:10px 11px;border-radius:10px;color:#475467;font-weight:600}.nav a:hover,.nav a.active{background:var(--primary-soft);color:#4546c8}.nav-icon{width:28px;height:28px;border-radius:8px;background:#f3f5f9;display:grid;place-items:center;font-size:13px}.nav a.active .nav-icon{background:#fff;color:#4f46e5}
.sidebar-bottom{margin-top:auto}.service{border:1px solid var(--line);border-radius:13px;padding:12px;background:#fbfcfe}.service-row{display:flex;align-items:center;justify-content:space-between;gap:8px}.dot{width:8px;height:8px;border-radius:999px;background:#98a2b3;box-shadow:0 0 0 4px #f2f4f7}.dot.ok{background:#22c55e;box-shadow:0 0 0 4px #dcfce7}.service-title{font-weight:700;font-size:12px}.service-meta{font-size:11px;color:var(--muted);margin-top:5px}
.main{margin-left:244px;min-height:100vh}.topbar{height:68px;border-bottom:1px solid rgba(229,233,242,.9);background:rgba(245,247,251,.8);backdrop-filter:blur(16px);display:flex;align-items:center;justify-content:space-between;padding:0 32px;position:sticky;top:0;z-index:15}.crumb{font-weight:700}.top-actions{display:flex;align-items:center;gap:9px}.mini{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 11px;color:#475467;font-weight:600}.mini:hover{border-color:#c9d0de;background:#fbfcff}
.content{max-width:1240px;margin:0 auto;padding:28px 30px 70px}
.hero{position:relative;overflow:hidden;border-radius:24px;padding:30px;background:linear-gradient(120deg,#ffffff 0%,#f8f8ff 58%,#f1efff 100%);border:1px solid #e7e8f7;box-shadow:var(--shadow);margin-bottom:20px}.hero:after{content:"";position:absolute;width:340px;height:340px;border-radius:999px;right:-120px;top:-180px;background:radial-gradient(circle,rgba(124,58,237,.16),rgba(124,58,237,0) 68%)}
.eyebrow{display:inline-flex;align-items:center;gap:7px;background:#fff;border:1px solid #e3e4f4;color:#5657c9;border-radius:999px;padding:6px 10px;font-size:11px;font-weight:750;letter-spacing:.02em}.hero h1{font-size:32px;line-height:1.2;letter-spacing:-.035em;margin:14px 0 10px;max-width:720px}.hero p{margin:0;color:var(--muted);font-size:15px;line-height:1.8;max-width:760px}.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:20px}.flow-step{background:rgba(255,255,255,.88);border:1px solid #e5e7f2;border-radius:10px;padding:8px 10px;font-weight:650;font-size:12px}.flow-arrow{color:#a0a8b8}
.section{scroll-margin-top:84px}.section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:24px 2px 12px}.section-title h2{margin:0;font-size:20px;letter-spacing:-.02em}.section-title p{margin:5px 0 0;color:var(--muted);font-size:12px}.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 5px 18px rgba(23,32,51,.035)}
.workbench{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.75fr);overflow:hidden}.editor{padding:22px 22px 24px;border-right:1px solid var(--line)}.config{padding:22px;background:#fbfcff}.panel-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.panel-title strong{font-size:14px}.subtle{font-size:11px;color:var(--muted)}
.quick-actions{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}.chip-btn{border:1px solid var(--line);background:#fff;color:#475467;border-radius:9px;padding:7px 10px;font-size:11px;font-weight:650}.chip-btn:hover{border-color:#c6c9ed;color:#4f46e5;background:#fafaff}.chip-btn.fail-demo:hover{color:#b42318;background:#fff8f7;border-color:#f2c9c5}
.upload{border:1px dashed #cfd5e2;background:#fafbff;border-radius:12px;padding:11px 13px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;gap:12px;transition:.2s}.upload.drag{border-color:#7778ea;background:#f6f5ff}.upload-left{display:flex;align-items:center;gap:9px}.upload-icon{width:34px;height:34px;border-radius:10px;background:var(--primary-soft);color:#5657d8;display:grid;place-items:center;font-weight:800}.upload strong{font-size:12px}.upload small{display:block;color:var(--muted);margin-top:2px}.upload button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 9px;font-size:11px;font-weight:700;color:#475467}#fileInput{display:none}
textarea{width:100%;min-height:280px;resize:vertical;border:1px solid var(--line-strong);border-radius:13px;padding:14px 15px;line-height:1.65;outline:none;color:var(--text);background:#fff;transition:.18s}textarea:focus,input:focus,select:focus{border-color:#8f8ff1;box-shadow:0 0 0 3px rgba(91,92,226,.09)}
.field{margin-bottom:15px}.field label{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:700;color:#344054;margin-bottom:7px}.field-hint{font-size:10px;color:#98a2b3;font-weight:500}.select,input[type=text],input[type=password],input[type=number]{width:100%;border:1px solid var(--line-strong);border-radius:10px;padding:9px 10px;outline:none;background:#fff;color:var(--text)}
.check-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.check-card{position:relative}.check-card input{position:absolute;opacity:0;pointer-events:none}.check-card label{display:block;text-align:center;border:1px solid var(--line);border-radius:9px;padding:9px 4px;background:#fff;color:#667085;font-weight:650;cursor:pointer;font-size:11px}.check-card input:checked+label{background:var(--primary-soft);border-color:#cfd0ff;color:#4d4ec6}
.range-wrap{display:grid;grid-template-columns:1fr 42px;gap:9px;align-items:center}.range-wrap input[type=range]{width:100%;accent-color:var(--primary)}.range-value{text-align:center;border:1px solid var(--line);border-radius:8px;padding:5px 0;background:#fff;font-weight:750;font-size:11px}
.switch-row{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid var(--line);border-radius:11px;background:#fff;padding:11px 12px;margin:13px 0}.switch-copy strong{font-size:12px}.switch-copy small{display:block;color:var(--muted);margin-top:3px}.switch{position:relative;width:40px;height:22px}.switch input{opacity:0;width:0;height:0}.slider{position:absolute;inset:0;background:#d0d5dd;border-radius:999px;transition:.2s}.slider:before{content:"";position:absolute;width:16px;height:16px;left:3px;top:3px;background:#fff;border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,.18);transition:.2s}.switch input:checked+.slider{background:linear-gradient(135deg,var(--primary),var(--primary-2))}.switch input:checked+.slider:before{transform:translateX(18px)}
.advanced{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}.advanced summary{font-size:11px;color:#667085;font-weight:700;cursor:pointer}.advanced-body{padding-top:12px}.two{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.primary-btn{width:100%;border:0;border-radius:11px;padding:12px 14px;background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;font-weight:800;box-shadow:0 9px 18px rgba(91,92,226,.22);transition:.18s}.primary-btn:hover{transform:translateY(-1px);box-shadow:0 11px 22px rgba(91,92,226,.27)}.primary-btn:disabled{opacity:.55;cursor:not-allowed;transform:none}.button-note{text-align:center;color:#98a2b3;font-size:10px;margin-top:8px}
.status-card{padding:20px 22px}.status-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.task-id{color:var(--muted);font-size:11px}.status-badge{font-size:11px;font-weight:750;border-radius:999px;padding:5px 9px;background:#f2f4f7;color:#667085}.status-badge.running{background:#eef4ff;color:#175cd3}.status-badge.done{background:var(--green-soft);color:var(--green)}.status-badge.failed{background:var(--red-soft);color:var(--red)}
.progress-track{height:7px;background:#eef1f5;border-radius:999px;margin:15px 0 12px;overflow:hidden}.progress-bar{height:100%;width:0;background:linear-gradient(90deg,var(--primary),#8b5cf6);border-radius:999px;transition:width .35s}.stage-line{display:flex;align-items:center;gap:7px;overflow-x:auto;padding-bottom:2px}.stage-pill{white-space:nowrap;font-size:10px;color:#98a2b3;border:1px solid var(--line);padding:5px 7px;border-radius:999px;background:#fff}.stage-pill.done{color:#4f46e5;background:#f5f3ff;border-color:#ddd6fe}.stage-pill.current{color:#fff;background:#6366f1;border-color:#6366f1}.status-message{font-size:11px;color:#667085;margin-top:10px}
.result-wrap{display:none}.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:13px}.metric{border:1px solid var(--line);border-radius:13px;padding:14px;background:#fff}.metric .value{font-size:24px;line-height:1;font-weight:800;letter-spacing:-.03em}.metric .label{font-size:10px;color:var(--muted);margin-top:6px}.metric .value.score{color:#5657d8}
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.tabs{display:flex;gap:5px;background:#f3f5f9;padding:4px;border-radius:10px;overflow:auto}.tab{border:0;background:transparent;padding:8px 10px;border-radius:7px;color:#667085;font-weight:700;font-size:11px;white-space:nowrap}.tab.active{background:#fff;color:#344054;box-shadow:0 1px 4px rgba(16,24,40,.07)}.exports{display:flex;gap:6px}.export-btn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 9px;font-size:10px;color:#475467;font-weight:700}.export-btn:hover{border-color:#c8cce8;color:#4f46e5}
.tab-panel{display:none}.tab-panel.active{display:block}.empty{border:1px dashed var(--line-strong);border-radius:13px;padding:28px;text-align:center;color:#98a2b3;background:#fbfcfe}
.case-card{border:1px solid var(--line);border-radius:13px;margin-bottom:9px;background:#fff;overflow:hidden}.case-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:13px 14px}.case-title{font-weight:800;font-size:13px}.case-meta{font-size:10px;color:var(--muted);margin-top:4px}.tags{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.tag{font-size:9px;font-weight:800;border-radius:999px;padding:4px 7px;background:#f2f4f7;color:#667085}.tag.p1{background:#fff1f0;color:#b42318}.tag.positive{background:#ecfdf3;color:#15803d}.tag.negative{background:#fff7ed;color:#b54708}.tag.edge{background:#eef4ff;color:#175cd3}.case-body{border-top:1px solid var(--line);padding:12px 14px;background:#fbfcfe}.precondition{font-size:10px;color:#667085;margin-bottom:9px}.steps{width:100%;border-collapse:collapse;font-size:10px}.steps th{text-align:left;color:#667085;padding:6px;border-bottom:1px solid var(--line);font-weight:700}.steps td{padding:7px 6px;border-bottom:1px solid #edf0f5;vertical-align:top;line-height:1.5}.steps tr:last-child td{border-bottom:0}
.req-table{width:100%;border-collapse:separate;border-spacing:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:11px}.req-table th{background:#f8f9fc;text-align:left;color:#667085;padding:9px;border-bottom:1px solid var(--line)}.req-table td{padding:10px 9px;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.5}.req-table tr:last-child td{border-bottom:0}.req-id{font-weight:800;color:#5556c7}
.review-layout{display:grid;grid-template-columns:220px 1fr;gap:12px}.score-card{border:1px solid var(--line);border-radius:13px;padding:18px;text-align:center;background:linear-gradient(180deg,#fbfbff,#fff)}.score-ring{width:108px;height:108px;border-radius:50%;margin:3px auto 12px;display:grid;place-items:center;background:conic-gradient(var(--primary) calc(var(--score)*1%),#ebeef4 0);position:relative}.score-ring:after{content:"";position:absolute;width:82px;height:82px;border-radius:50%;background:#fff}.score-num{position:relative;z-index:2;font-size:26px;font-weight:850}.score-label{font-size:10px;color:var(--muted)}.review-block{border:1px solid var(--line);border-radius:13px;padding:14px;background:#fff;margin-bottom:9px}.review-block h4{margin:0 0 8px;font-size:12px}.bullet{font-size:11px;color:#475467;line-height:1.6;margin:4px 0}.context-card{border:1px solid var(--line);background:#fbfcff;border-radius:11px;padding:11px 12px;margin:7px 0;font-size:10px;color:#475467;line-height:1.6;white-space:pre-wrap}
.exec-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:12px}.exec-case{border:1px solid var(--line);border-radius:12px;padding:12px;margin:8px 0}.exec-head{display:flex;justify-content:space-between;gap:12px}.exec-title{font-weight:800;font-size:12px}.exec-meta{font-size:10px;color:var(--muted);margin-top:4px}.badge{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:9px;font-weight:850}.pass{background:var(--green-soft);color:var(--green)}.fail{background:var(--red-soft);color:var(--red)}.skip{background:var(--amber-soft);color:var(--amber)}.failure{border-left:3px solid #ef4444;background:#fff7f6;border-radius:9px;padding:11px 12px;margin:9px 0}.failure strong{color:var(--red);font-size:11px}.failure div{font-size:10px;color:#475467;line-height:1.55;margin-top:3px}
pre{white-space:pre-wrap;word-break:break-word;background:#101828;color:#d0d5dd;border-radius:12px;padding:14px;max-height:520px;overflow:auto;font-size:10px;line-height:1.55}.raw-card{border:1px solid var(--line);border-radius:12px;overflow:hidden}.raw-top{padding:9px 12px;background:#f8f9fc;border-bottom:1px solid var(--line);font-size:10px;color:#667085;font-weight:700}.raw-card pre{border-radius:0;margin:0}
.toast{position:fixed;right:24px;bottom:24px;background:#101828;color:#fff;border-radius:11px;padding:11px 13px;font-size:11px;box-shadow:0 12px 30px rgba(16,24,40,.2);opacity:0;transform:translateY(8px);pointer-events:none;transition:.22s;z-index:50}.toast.show{opacity:1;transform:translateY(0)}.toast.error{background:#991b1b}
@media(max-width:1000px){.sidebar{display:none}.main{margin-left:0}.workbench{grid-template-columns:1fr}.editor{border-right:0;border-bottom:1px solid var(--line)}.review-layout{grid-template-columns:1fr}.topbar{padding:0 20px}.content{padding:22px 18px 60px}}
@media(max-width:720px){.hero{padding:22px}.hero h1{font-size:26px}.summary-grid,.exec-grid{grid-template-columns:repeat(2,1fr)}.toolbar{align-items:flex-start;flex-direction:column}.exports{width:100%;flex-wrap:wrap}.two{grid-template-columns:1fr}.workbench .editor,.workbench .config{padding:16px}.content{padding:16px 12px 50px}.topbar{height:58px}}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">R2</div>
      <div><div class="brand-title">Req2Test Agent</div><div class="brand-sub">AI Test Workbench</div></div>
    </div>
    <div class="nav-label">工作区</div>
    <nav class="nav">
      <a class="active" href="#create"><span class="nav-icon">＋</span><span>新建测试任务</span></a>
      <a href="#status"><span class="nav-icon">↻</span><span>任务进度</span></a>
      <a href="#results"><span class="nav-icon">✓</span><span>生成与执行结果</span></a>
    </nav>
    <div class="sidebar-bottom">
      <div class="service">
        <div class="service-row"><div><div class="service-title">平台服务</div><div class="service-meta" id="serviceMeta">正在检查...</div></div><span class="dot" id="serviceDot"></span></div>
      </div>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="crumb">AI 测试工作台</div>
      <div class="top-actions">
        <button class="mini" onclick="loadBusinessDemo()">业务需求示例</button>
        <a class="mini" href="https://github.com/xingqianyue268-alt/req2test-agent" target="_blank" rel="noreferrer">GitHub ↗</a>
      </div>
    </header>

    <div class="content">
      <section class="hero">
        <span class="eyebrow">✦ AI Test Design + Execution</span>
        <h1>从需求文档到可执行测试，一条链路完成设计、评审与验证</h1>
        <p>输入业务需求或接口契约，平台先通过 RAG 与多智能体生成结构化测试用例并自动评审；对具备明确 API 契约的场景，还可继续调用 HTTP Tool 与 Pytest 真实执行，并对失败结果进行归因。</p>
        <div class="flow">
          <span class="flow-step">1. 输入需求</span><span class="flow-arrow">→</span>
          <span class="flow-step">2. RAG 检索</span><span class="flow-arrow">→</span>
          <span class="flow-step">3. AI 生成与评审</span><span class="flow-arrow">→</span>
          <span class="flow-step">4. 可选真实执行</span><span class="flow-arrow">→</span>
          <span class="flow-step">5. 失败归因与导出</span>
        </div>
      </section>

      <section class="section" id="create">
        <div class="section-head"><div class="section-title"><h2>新建测试任务</h2><p>支持粘贴需求，也支持 TXT / Markdown / DOCX / 可复制文本 PDF。</p></div></div>
        <div class="card workbench">
          <div class="editor">
            <div class="panel-title"><strong>需求输入</strong><span class="subtle" id="charCount">0 字符</span></div>
            <div class="quick-actions">
              <button class="chip-btn" onclick="loadBusinessDemo()">业务需求示例</button>
              <button class="chip-btn" onclick="loadPassDemo()">API 全通过示例</button>
              <button class="chip-btn fail-demo" onclick="loadFailDemo()">API 失败归因示例</button>
            </div>
            <div class="upload" id="dropZone">
              <div class="upload-left"><div class="upload-icon">⇧</div><div><strong id="uploadTitle">导入需求文档</strong><small id="uploadSub">拖拽文件到这里，或选择本地文件</small></div></div>
              <button type="button" onclick="document.getElementById('fileInput').click()">选择文件</button>
              <input id="fileInput" type="file" accept=".txt,.md,.docx,.pdf" />
            </div>
            <textarea id="req" placeholder="粘贴需求清单、操作手册、PRD 或明确的 HTTP API 契约..."></textarea>
          </div>

          <div class="config">
            <div class="panel-title"><strong>生成配置</strong><span class="subtle">Generation Config</span></div>
            <div class="field"><label>测试类型 <span class="field-hint">至少选择一种</span></label>
              <div class="check-grid">
                <div class="check-card"><input id="positive" type="checkbox" checked><label for="positive">正向</label></div>
                <div class="check-card"><input id="negative" type="checkbox" checked><label for="negative">异常</label></div>
                <div class="check-card"><input id="edge" type="checkbox"><label for="edge">边界</label></div>
              </div>
            </div>
            <div class="field"><label>最多生成用例数 <span class="field-hint">1–60</span></label><div class="range-wrap"><input id="maxCases" type="range" min="1" max="30" value="12"><div class="range-value" id="maxCasesValue">12</div></div></div>
            <div class="field"><label>最低评审分数 <span class="field-hint">低于阈值自动修订</span></label><div class="range-wrap"><input id="reviewScore" type="range" min="60" max="100" value="85"><div class="range-value" id="reviewScoreValue">85</div></div></div>

            <div class="switch-row">
              <div class="switch-copy"><strong>同时执行可执行 API 测试</strong><small>HTTP Tool + Pytest + 失败归因</small></div>
              <label class="switch"><input id="execute" type="checkbox"><span class="slider"></span></label>
            </div>
            <div class="field" id="baseUrlField" style="display:none"><label for="baseUrl">被测服务 Base URL <span class="field-hint">Docker Demo 默认 http://api:8000</span></label><input id="baseUrl" type="text" value="http://api:8000"></div>

            <details class="advanced">
              <summary>模型设置（可选）</summary>
              <div class="advanced-body">
                <div class="field"><label for="mode">运行模式</label><select class="select" id="mode"><option value="demo">离线演示模式</option><option value="openai_compatible">OpenAI 兼容接口</option></select></div>
                <div id="modelFields" style="display:none">
                  <div class="two"><div class="field"><label for="model">模型</label><input id="model" type="text" value="gpt-4.1-mini"></div><div class="field"><label for="apiKey">API Key</label><input id="apiKey" type="password" placeholder="仅本次任务使用"></div></div>
                  <div class="field"><label for="llmBaseUrl">模型 Base URL</label><input id="llmBaseUrl" type="text" value="https://api.openai.com/v1"></div>
                </div>
              </div>
            </details>
            <button class="primary-btn" id="submitBtn" onclick="submitTask()">✦ AI 生成并评审测试用例</button>
            <div class="button-note" id="submitNote">生成完成后可查看用例、需求拆分、评审与 RAG 依据</div>
          </div>
        </div>
      </section>

      <section class="section" id="status">
        <div class="section-head"><div class="section-title"><h2>任务进度</h2><p>异步任务由 RabbitMQ / Celery 执行，进度通过 WebSocket 实时回传。</p></div></div>
        <div class="card status-card">
          <div class="status-top"><div class="task-id" id="taskId">尚未提交任务</div><span class="status-badge" id="statusBadge">IDLE</span></div>
          <div class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
          <div class="stage-line" id="stageLine"></div>
          <div class="status-message" id="message">提交任务后，这里会显示检索、分析、设计、评审和执行阶段。</div>
        </div>
      </section>

      <section class="section" id="results">
        <div class="section-head"><div class="section-title"><h2>生成与执行结果</h2><p>先看测试设计质量，再按需查看真实接口执行与失败归因。</p></div></div>
        <div class="card" style="padding:18px">
          <div id="resultEmpty" class="empty">完成一次测试任务后，这里会展示测试用例、需求拆分、评审报告、RAG 依据与执行结果。</div>
          <div class="result-wrap" id="resultWrap">
            <div class="summary-grid">
              <div class="metric"><div class="value" id="reqCount">0</div><div class="label">需求项</div></div>
              <div class="metric"><div class="value" id="caseCount">0</div><div class="label">测试用例</div></div>
              <div class="metric"><div class="value score" id="scoreValue">0</div><div class="label">评审得分</div></div>
              <div class="metric"><div class="value" id="coverageValue">0%</div><div class="label">需求覆盖率</div></div>
            </div>
            <div class="toolbar">
              <div class="tabs">
                <button class="tab active" data-tab="cases" onclick="switchTab('cases',this)">测试用例</button>
                <button class="tab" data-tab="requirements" onclick="switchTab('requirements',this)">需求拆分</button>
                <button class="tab" data-tab="review" onclick="switchTab('review',this)">评审 & RAG</button>
                <button class="tab" data-tab="execution" onclick="switchTab('execution',this)">执行结果</button>
                <button class="tab" data-tab="raw" onclick="switchTab('raw',this)">原始 JSON</button>
              </div>
              <div class="exports"><button class="export-btn" onclick="downloadResult('md')">Markdown</button><button class="export-btn" onclick="downloadResult('csv')">CSV</button><button class="export-btn" onclick="downloadResult('json')">JSON</button></div>
            </div>
            <div class="tab-panel active" id="panel-cases"></div>
            <div class="tab-panel" id="panel-requirements"></div>
            <div class="tab-panel" id="panel-review"></div>
            <div class="tab-panel" id="panel-execution"></div>
            <div class="tab-panel" id="panel-raw"><div class="raw-card"><div class="raw-top">完整任务结果 · 用于调试和深入查看</div><pre id="rawResult"></pre></div></div>
          </div>
        </div>
      </section>
    </div>
  </main>
</div>
<div class="toast" id="toast"></div>

<script>
const BUSINESS_DEMO=`# 供应商管理需求
用户进入供应商管理页面后，可以新增供应商。
填写供应商名称、联系人和联系电话后点击保存，系统提示保存成功，并在供应商列表中显示新记录。
当供应商名称为空时，不允许提交，并提示必填信息。
列表支持按照供应商名称进行查询。`;
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
const STAGES=[['queued','排队'],['started','接收'],['retrieval','RAG检索'],['analysis','需求分析'],['design','用例设计'],['review','质量评审'],['revision','自动修订'],['generation_completed','生成完成'],['tool_planning','执行规划'],['failure_analysis','失败归因'],['completed','完成']];
let currentResult=null;
let currentTaskId='';

function esc(value){return String(value??'').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]))}
function toast(message,error=false){const el=document.getElementById('toast');el.textContent=message;el.className='toast show'+(error?' error':'');setTimeout(()=>el.className='toast',2600)}
function updateChars(){document.getElementById('charCount').textContent=document.getElementById('req').value.length+' 字符'}
function setExecution(enabled){document.getElementById('execute').checked=enabled;document.getElementById('baseUrlField').style.display=enabled?'block':'none';document.getElementById('submitBtn').textContent=enabled?'✦ AI 生成、评审并执行测试':'✦ AI 生成并评审测试用例';document.getElementById('submitNote').textContent=enabled?'对显式 API 契约继续执行 HTTP Tool 与 Pytest':'生成完成后可查看用例、需求拆分、评审与 RAG 依据'}
function loadBusinessDemo(){document.getElementById('req').value=BUSINESS_DEMO;setExecution(false);updateChars();location.hash='#create'}
function loadPassDemo(){document.getElementById('req').value=PASS_DEMO;setExecution(true);updateChars();location.hash='#create'}
function loadFailDemo(){document.getElementById('req').value=FAIL_DEMO;setExecution(true);updateChars();location.hash='#create'}

function renderStages(stage){
  const currentIndex=Math.max(0,STAGES.findIndex(x=>x[0]===stage));
  document.getElementById('stageLine').innerHTML=STAGES.map((s,i)=>`<span class="stage-pill ${i<currentIndex?'done':i===currentIndex&&stage!=='queued'?'current':''}">${esc(s[1])}</span>`).join('');
}
renderStages('queued');

async function checkHealth(){
  try{const r=await fetch('/health');const d=await r.json();if(r.ok&&d.status==='ok'){document.getElementById('serviceDot').classList.add('ok');document.getElementById('serviceMeta').textContent='API 在线 · '+(d.task_store||'store')}}catch(e){document.getElementById('serviceMeta').textContent='连接失败'}
}
checkHealth();

function fileToBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file)})}
async function parseFile(file){
  if(!file)return;
  if(file.size>10*1024*1024){toast('文件不能超过 10 MB',true);return}
  document.getElementById('uploadTitle').textContent='正在解析 '+file.name;
  document.getElementById('uploadSub').textContent='请稍候...';
  try{
    const content_base64=await fileToBase64(file);
    const r=await fetch('/api/v1/documents/parse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,content_base64})});
    const d=await r.json();if(!r.ok)throw new Error(d.detail||'文档解析失败');
    document.getElementById('req').value=d.text;updateChars();document.getElementById('uploadTitle').textContent=file.name;document.getElementById('uploadSub').textContent=`已解析 ${d.characters} 字符，可继续编辑`;toast('需求文档已导入');
  }catch(e){document.getElementById('uploadTitle').textContent='导入需求文档';document.getElementById('uploadSub').textContent='拖拽文件到这里，或选择本地文件';toast(e.message||'文档解析失败',true)}
}
const fileInput=document.getElementById('fileInput');fileInput.addEventListener('change',e=>parseFile(e.target.files[0]));
const dropZone=document.getElementById('dropZone');['dragenter','dragover'].forEach(name=>dropZone.addEventListener(name,e=>{e.preventDefault();dropZone.classList.add('drag')}));['dragleave','drop'].forEach(name=>dropZone.addEventListener(name,e=>{e.preventDefault();dropZone.classList.remove('drag')}));dropZone.addEventListener('drop',e=>parseFile(e.dataTransfer.files[0]));

document.getElementById('req').addEventListener('input',updateChars);
document.getElementById('maxCases').addEventListener('input',e=>document.getElementById('maxCasesValue').textContent=e.target.value);
document.getElementById('reviewScore').addEventListener('input',e=>document.getElementById('reviewScoreValue').textContent=e.target.value);
document.getElementById('execute').addEventListener('change',e=>setExecution(e.target.checked));
document.getElementById('mode').addEventListener('change',e=>document.getElementById('modelFields').style.display=e.target.value==='openai_compatible'?'block':'none');
loadBusinessDemo();

async function submitTask(){
  const requirement_text=document.getElementById('req').value.trim();if(!requirement_text){toast('请先输入或导入需求内容',true);return}
  const include_positive=document.getElementById('positive').checked,include_negative=document.getElementById('negative').checked,include_edge=document.getElementById('edge').checked;if(!include_positive&&!include_negative&&!include_edge){toast('至少选择一种测试类型',true);return}
  const enabled=document.getElementById('execute').checked;
  const submit=document.getElementById('submitBtn');submit.disabled=true;submit.textContent='正在创建任务...';
  document.getElementById('taskId').textContent='正在提交';document.getElementById('statusBadge').className='status-badge running';document.getElementById('statusBadge').textContent='SUBMITTING';document.getElementById('progressBar').style.width='2%';document.getElementById('message').textContent='正在创建异步测试任务';renderStages('queued');
  const payload={
    requirement_text,
    llm_settings:{mode:document.getElementById('mode').value,model:document.getElementById('model').value||'gpt-4.1-mini',base_url:document.getElementById('llmBaseUrl').value||'https://api.openai.com/v1',api_key:document.getElementById('apiKey').value||''},
    generation_config:{include_positive,include_negative,include_edge,max_cases:Number(document.getElementById('maxCases').value),min_review_score:Number(document.getElementById('reviewScore').value),max_review_iterations:1},
    execution_config:{enabled,base_url:enabled?document.getElementById('baseUrl').value.trim():'',run_http_tool:true,run_pytest:true}
  };
  try{
    const resp=await fetch('/api/v1/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await resp.json();if(!resp.ok)throw new Error(data.detail?JSON.stringify(data.detail):'提交失败');
    currentTaskId=data.task_id;document.getElementById('taskId').textContent='Task ID · '+data.task_id;document.getElementById('statusBadge').textContent='RUNNING';location.hash='#status';
    const scheme=location.protocol==='https:'?'wss':'ws';const ws=new WebSocket(`${scheme}://${location.host}${data.ws_url}`);
    ws.onmessage=(event)=>{const state=JSON.parse(event.data);updateTaskState(state);if(state.result){currentResult=state.result;renderResult(state.result);submit.disabled=false;setExecution(document.getElementById('execute').checked)}if(state.status==='failed'){submit.disabled=false;setExecution(document.getElementById('execute').checked)}};
    ws.onerror=()=>toast('WebSocket 连接异常，可稍后通过 Task ID 查询',true);
  }catch(e){submit.disabled=false;setExecution(document.getElementById('execute').checked);document.getElementById('statusBadge').className='status-badge failed';document.getElementById('statusBadge').textContent='FAILED';document.getElementById('message').textContent=e.message;toast(e.message||'任务提交失败',true)}
}
function updateTaskState(state){
  const progress=state.progress||0,stage=state.stage||'queued';document.getElementById('progressBar').style.width=progress+'%';document.getElementById('message').textContent=(state.message||stage)+` · ${progress}%`;renderStages(stage);
  const badge=document.getElementById('statusBadge');if(state.status==='completed'){badge.className='status-badge done';badge.textContent='COMPLETED'}else if(state.status==='failed'){badge.className='status-badge failed';badge.textContent='FAILED'}else{badge.className='status-badge running';badge.textContent=String(stage).toUpperCase()}
}

function typeClass(type){const t=String(type||'').toLowerCase();if(t.includes('正')||t.includes('positive'))return 'positive';if(t.includes('异常')||t.includes('negative'))return 'negative';if(t.includes('边界')||t.includes('edge'))return 'edge';return ''}
function renderResult(result){
  document.getElementById('resultEmpty').style.display='none';document.getElementById('resultWrap').style.display='block';
  const requirements=result.requirements||[],cases=result.test_cases||[],review=result.review||{};document.getElementById('reqCount').textContent=requirements.length;document.getElementById('caseCount').textContent=cases.length;document.getElementById('scoreValue').textContent=review.score??'-';document.getElementById('coverageValue').textContent=review.coverage_rate!=null?Math.round(review.coverage_rate*100)+'%':'-';
  document.getElementById('rawResult').textContent=JSON.stringify(result,null,2);renderCases(cases);renderRequirements(requirements);renderReview(result);renderExecution(result.execution);location.hash='#results';
}
function renderCases(cases){
  const panel=document.getElementById('panel-cases');if(!cases.length){panel.innerHTML='<div class="empty">没有生成测试用例</div>';return}
  panel.innerHTML=cases.map(c=>`<div class="case-card"><div class="case-head"><div><div class="case-title">${esc(c.case_id)} · ${esc(c.title)}</div><div class="case-meta">模块：${esc(c.module||'-')} · 来源：${esc(c.source_requirement||'-')}</div></div><div class="tags"><span class="tag ${String(c.priority||'').toLowerCase()==='p1'?'p1':''}">${esc(c.priority||'P?')}</span><span class="tag ${typeClass(c.test_type)}">${esc(c.test_type||'测试')}</span></div></div><div class="case-body"><div class="precondition">前置条件：${esc((c.preconditions||[]).join('；')||'无特殊前置条件')}</div><table class="steps"><thead><tr><th style="width:48px">序号</th><th>输入 / 操作描述</th><th>预期结果</th></tr></thead><tbody>${(c.steps||[]).map(s=>`<tr><td>${esc(s.order)}</td><td>${esc(s.action)}</td><td>${esc(s.expected)}</td></tr>`).join('')}</tbody></table></div></div>`).join('')
}
function renderRequirements(requirements){
  const panel=document.getElementById('panel-requirements');if(!requirements.length){panel.innerHTML='<div class="empty">暂无需求拆分结果</div>';return}
  panel.innerHTML=`<table class="req-table"><thead><tr><th>编号</th><th>模块</th><th>需求描述</th><th>验收标准</th></tr></thead><tbody>${requirements.map(r=>`<tr><td class="req-id">${esc(r.requirement_id)}</td><td>${esc(r.module||'-')}</td><td>${esc(r.description||'')}</td><td>${esc((r.acceptance_criteria||[]).join('；')||'-')}</td></tr>`).join('')}</tbody></table>`
}
function renderReview(result){
  const review=result.review||{},contexts=result.retrieved_context||[],issues=review.issues||[],suggestions=review.suggestions||[],score=Number(review.score||0);document.getElementById('panel-review').innerHTML=`<div class="review-layout"><div class="score-card"><div class="score-ring" style="--score:${Math.max(0,Math.min(score,100))}"><span class="score-num">${esc(review.score??'-')}</span></div><div class="score-label">质量评审得分</div><div style="font-size:11px;margin-top:9px;color:#475467">覆盖率 ${review.coverage_rate!=null?Math.round(review.coverage_rate*100)+'%':'-'}</div></div><div><div class="review-block"><h4>评审结论</h4>${issues.length?issues.map(i=>`<div class="bullet">• ${esc(i)}</div>`).join(''):'<div class="bullet">✓ 未发现结构性问题</div>'}${suggestions.length?'<h4 style="margin-top:11px">改进建议</h4>'+suggestions.map(i=>`<div class="bullet">• ${esc(i)}</div>`).join(''):''}</div><div class="review-block"><h4>RAG 检索依据 <span class="subtle">'+contexts.length+' 条</span></h4>${contexts.length?contexts.map((c,i)=>`<div class="context-card"><strong>Context ${i+1}</strong>\n${esc(c)}</div>`).join(''):'<div class="bullet">本次未返回检索上下文</div>'}</div></div></div>`
}
function renderExecution(execution){
  const panel=document.getElementById('panel-execution');if(!execution||!execution.enabled){panel.innerHTML='<div class="empty">本次任务仅完成测试设计与评审。需要真实执行时，请在新建任务中开启“同时执行可执行 API 测试”。</div>';return}
  const summary=execution.summary||{},results=execution.http_results||[],failures=execution.failure_analysis||[],pytest=execution.pytest_result;panel.innerHTML=`<div class="exec-grid"><div class="metric"><div class="value">${esc(summary.total_http_cases??results.length)}</div><div class="label">HTTP 用例</div></div><div class="metric"><div class="value">${esc(summary.passed_http_cases??0)}</div><div class="label">HTTP 通过</div></div><div class="metric"><div class="value">${esc(summary.failed_http_cases??0)}</div><div class="label">HTTP 失败</div></div><div class="metric"><div class="value">${pytest?`<span class="badge ${pytest.passed?'pass':'fail'}">${pytest.passed?'PASS':'FAIL'}</span>`:'<span class="badge skip">SKIP</span>'}</div><div class="label">Pytest</div></div></div>${results.map(item=>`<div class="exec-case"><div class="exec-head"><div><div class="exec-title">${esc(item.method)} ${esc(pathname(item.url))}</div><div class="exec-meta">${esc(item.case_id)} · ${esc(item.duration_ms??'-')} ms · expected ${esc(item.expected_status)} / actual ${esc(item.status_code??'-')}</div></div><span class="badge ${item.passed?'pass':'fail'}">${item.passed?'PASS':'FAIL'}</span></div>${item.failures&&item.failures.length?`<div class="exec-meta" style="margin-top:8px">${esc(item.failures.join('；'))}</div>`:''}</div>`).join('')}${failures.length?'<h3 style="font-size:13px;margin:16px 0 8px">失败归因</h3>'+failures.map(f=>`<div class="failure"><strong>${esc(f.case_id)} · ${esc(f.category)}</strong><div>${esc(f.probable_cause)}</div><div>证据：${esc((f.evidence||[]).join('；')||'-')}</div><div>建议：${esc(f.suggestion||'-')}</div></div>`).join(''):''}`
}
function pathname(url){try{return new URL(url).pathname}catch(e){return url||'-'}}
function switchTab(name,button){document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab-panel').forEach(x=>x.classList.remove('active'));button.classList.add('active');document.getElementById('panel-'+name).classList.add('active')}

function downloadBlob(text,type,name){const blob=new Blob([text],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),500)}
function csvCell(v){const s=String(v??'').replace(/"/g,'""');return `"${s}"`}
function toMarkdown(result){let out='# Req2Test 测试结果\n\n';out+=`- 需求项：${(result.requirements||[]).length}\n- 测试用例：${(result.test_cases||[]).length}\n- 评审得分：${result.review?.score??'-'}\n- 覆盖率：${result.review?.coverage_rate!=null?Math.round(result.review.coverage_rate*100)+'%':'-'}\n\n`;for(const c of result.test_cases||[]){out+=`## ${c.case_id} ${c.title}\n\n- 模块：${c.module||'-'}\n- 优先级：${c.priority||'-'}\n- 类型：${c.test_type||'-'}\n- 来源需求：${c.source_requirement||'-'}\n\n| 序号 | 输入/操作描述 | 预期结果 |\n|---|---|---|\n`;for(const s of c.steps||[])out+=`| ${s.order} | ${String(s.action||'').replace(/\|/g,'\\|')} | ${String(s.expected||'').replace(/\|/g,'\\|')} |\n`;out+='\n'}return out}
function toCsv(result){const rows=[['用例编号','模块','用例名称','优先级','测试类型','来源需求','步骤序号','输入/操作描述','预期结果']];for(const c of result.test_cases||[]){for(const s of c.steps||[])rows.push([c.case_id,c.module,c.title,c.priority,c.test_type,c.source_requirement,s.order,s.action,s.expected])}return '\ufeff'+rows.map(r=>r.map(csvCell).join(',')).join('\n')}
function downloadResult(type){if(!currentResult){toast('暂无可导出结果',true);return}if(type==='json')downloadBlob(JSON.stringify(currentResult,null,2),'application/json','req2test_result.json');if(type==='md')downloadBlob(toMarkdown(currentResult),'text/markdown','req2test_cases.md');if(type==='csv')downloadBlob(toCsv(currentResult),'text/csv','req2test_cases.csv')}
</script>
</body>
</html>
"""
