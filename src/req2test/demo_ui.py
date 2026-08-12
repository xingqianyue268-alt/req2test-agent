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

/* Unified light-glass workbench */
:root{
  --page-bg:#e7eef7;--glass:rgba(255,255,255,.50);--glass-strong:rgba(255,255,255,.72);
  --text:#172033;--muted:#667085;--primary:#5b6cff;--primary-2:#7c66ff;
  --primary-soft:rgba(91,108,255,.10);--green:#16845b;--green-soft:#e9f7f0;
  --red:#d7444a;--red-soft:#fff0f1;--line:rgba(255,255,255,.64);
  --line-strong:rgba(139,157,190,.28);--shadow:0 18px 50px rgba(65,84,125,.12),inset 0 1px 0 rgba(255,255,255,.75);
  --radius:22px;
}
body{
  min-width:320px;background:
    radial-gradient(circle at 12% 8%,rgba(255,255,255,.94) 0,rgba(255,255,255,0) 28%),
    radial-gradient(circle at 88% 5%,rgba(114,164,221,.30) 0,rgba(114,164,221,0) 32%),
    radial-gradient(circle at 75% 78%,rgba(159,138,225,.14) 0,rgba(159,138,225,0) 30%),
    linear-gradient(135deg,#edf2f8 0%,#dce8f5 52%,#e8edf7 100%);
  background-attachment:fixed;font-size:14px;
}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.35;background-image:linear-gradient(rgba(255,255,255,.11) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.11) 1px,transparent 1px);background-size:44px 44px;mask-image:linear-gradient(to bottom,black,transparent 74%)}
.shell{position:relative}
.sidebar{
  inset:12px auto 12px 12px;width:250px;border:1px solid rgba(255,255,255,.76);border-radius:24px;
  padding:20px 14px;background:rgba(239,245,252,.54);box-shadow:0 20px 54px rgba(53,70,105,.15),inset 0 1px 0 rgba(255,255,255,.9);
  backdrop-filter:blur(26px) saturate(145%);-webkit-backdrop-filter:blur(26px) saturate(145%);
}
.brand{padding:4px 8px 24px}.brand-mark{width:42px;height:42px;border-radius:14px;background:linear-gradient(145deg,#5065ef,#7969e9);box-shadow:0 10px 24px rgba(70,85,204,.25),inset 0 1px 0 rgba(255,255,255,.38)}
.brand-title{font-size:16px}.brand-sub{font-size:10px;letter-spacing:.035em}
.nav-label{padding:0 11px 9px;color:#8793a8}
.nav{gap:6px}.nav a{position:relative;padding:9px 10px;border:1px solid transparent;border-radius:13px;color:#526078;transition:background .22s ease-out,border-color .22s ease-out,color .22s ease-out,transform .22s ease-out}
.nav a:hover{transform:translateX(2px);background:rgba(255,255,255,.43);border-color:rgba(255,255,255,.55);color:#34425d}
.nav a.active{background:rgba(255,255,255,.72);border-color:rgba(255,255,255,.86);color:#4251cf;box-shadow:0 10px 24px rgba(69,85,127,.09),inset 0 1px 0 #fff}
.nav a.active:before{content:"";position:absolute;left:-4px;width:3px;height:20px;border-radius:10px;background:#5b6cff;box-shadow:0 0 12px rgba(91,108,255,.4)}
.nav-icon{width:30px;height:30px;background:rgba(255,255,255,.44);border:1px solid rgba(255,255,255,.56);font-size:12px}
.nav a.active .nav-icon{background:rgba(91,108,255,.1)}
.service{border-color:rgba(255,255,255,.66);border-radius:15px;background:rgba(255,255,255,.48);box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.main{margin-left:274px}.topbar{height:72px;border:0;background:transparent;padding:0 34px;backdrop-filter:none}
.header-title{font-size:15px;font-weight:800;letter-spacing:-.01em}.header-sub{font-size:10px;color:var(--muted);margin-top:3px;letter-spacing:.02em}
.health-pill{display:inline-flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.7);background:rgba(255,255,255,.54);border-radius:999px;padding:8px 11px;color:#496176;font-size:11px;font-weight:700;box-shadow:inset 0 1px 0 rgba(255,255,255,.9)}
.health-pill .dot{width:7px;height:7px;box-shadow:0 0 0 4px rgba(34,160,107,.10)}
.mini{border-color:rgba(255,255,255,.72);background:rgba(255,255,255,.52);border-radius:11px;box-shadow:inset 0 1px 0 rgba(255,255,255,.9);transition:.2s ease-out}
.mini:hover{background:rgba(255,255,255,.8);transform:translateY(-1px)}
.content{max-width:1420px;padding:8px 34px 72px}
.hero{min-height:268px;display:flex;flex-direction:column;justify-content:center;padding:38px 40px;margin-bottom:26px;border:1px solid rgba(255,255,255,.72);background:linear-gradient(115deg,rgba(255,255,255,.72),rgba(241,246,252,.48) 58%,rgba(218,229,245,.50));box-shadow:var(--shadow);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px)}
.hero:before{content:"";position:absolute;right:4%;top:18%;width:210px;height:210px;border-radius:50%;border:1px solid rgba(255,255,255,.45);box-shadow:0 0 0 28px rgba(255,255,255,.08),0 0 0 56px rgba(112,132,209,.045)}
.hero:after{width:440px;height:440px;right:-70px;top:-200px;background:radial-gradient(circle,rgba(108,125,226,.20),rgba(108,125,226,0) 67%)}
.hero>*{position:relative;z-index:1}.eyebrow{width:max-content;background:rgba(255,255,255,.64);border-color:rgba(255,255,255,.82);color:#4e5dcc;box-shadow:inset 0 1px 0 #fff}
.hero h1{font-size:38px;max-width:760px;margin:14px 0 8px}.hero p{font-size:15px;line-height:1.65;max-width:720px}.hero-en{font-weight:620;color:#536078!important;letter-spacing:.012em}.flow{margin-top:22px;gap:7px}.flow-step{background:rgba(255,255,255,.60);border-color:rgba(255,255,255,.8);border-radius:999px;padding:8px 12px;box-shadow:inset 0 1px 0 #fff;color:#37445b}.flow-arrow{color:#75839a}
.section{scroll-margin-top:84px}.section-head{margin:30px 3px 13px}.section-title h2{font-size:21px}.section-title p{font-size:12px;color:#66738a}
.card,.metric,.case-card,.review-block,.score-card,.exec-case,.raw-card{background:var(--glass);border-color:rgba(255,255,255,.68);box-shadow:var(--shadow);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)}
.workbench{grid-template-columns:minmax(0,1.55fr) minmax(340px,.72fr);border-radius:24px}.editor{padding:25px;border-right-color:rgba(255,255,255,.55)}.config{padding:25px;background:rgba(245,248,253,.42)}
.panel-title strong{font-size:15px}.quick-actions{gap:8px}.chip-btn,.upload button,.export-btn{border-color:rgba(255,255,255,.75);background:rgba(255,255,255,.58);box-shadow:inset 0 1px 0 #fff;transition:.2s ease-out}.chip-btn:hover,.upload button:hover,.export-btn:hover{background:rgba(255,255,255,.88);transform:translateY(-1px)}
.upload{border-color:rgba(129,148,185,.34);background:rgba(255,255,255,.28);padding:13px 14px}.upload-icon{background:rgba(91,108,255,.10);border:1px solid rgba(255,255,255,.66)}
textarea,.select,input[type=text],input[type=password],input[type=number]{background:rgba(255,255,255,.62);border-color:rgba(121,141,177,.28);box-shadow:inset 0 1px 0 rgba(255,255,255,.86)}
textarea{min-height:306px;border-radius:16px;padding:16px}.check-card label{background:rgba(255,255,255,.42);border-color:rgba(255,255,255,.62);border-radius:11px}.check-card input:checked+label{background:rgba(91,108,255,.11);border-color:rgba(91,108,255,.28);color:#4553c8;box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.switch-row{background:rgba(255,255,255,.42);border-color:rgba(255,255,255,.7);border-radius:14px}.execution-tools{display:none;grid-template-columns:1fr 1fr;gap:8px;margin:-5px 0 14px}.tool-token{display:flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.68);background:rgba(255,255,255,.35);padding:9px 10px;border-radius:11px;color:#536078;font-size:10px;font-weight:700}.tool-token span{display:grid;place-items:center;width:24px;height:24px;border-radius:8px;background:rgba(91,108,255,.1);color:#4e5dcc}
.advanced{border-top-color:rgba(133,151,181,.22);margin-top:14px}.advanced summary{padding:3px 0;color:#526078}.advanced-body{animation:fadeReveal .25s ease-out}
.primary-btn{position:relative;overflow:hidden;border-radius:13px;padding:13px;background:linear-gradient(135deg,#5367ed,#7465e7);box-shadow:0 12px 25px rgba(77,90,202,.22),inset 0 1px 0 rgba(255,255,255,.35)}
.primary-btn:after{content:"";position:absolute;inset:-2px auto -2px -45%;width:32%;transform:skewX(-18deg);background:linear-gradient(90deg,transparent,rgba(255,255,255,.28),transparent);transition:left .4s ease-out}.primary-btn:hover:after{left:115%}
.status-card{padding:24px;border-radius:22px}.status-top{margin-bottom:18px}.progress-track{height:5px;background:rgba(114,132,165,.13);margin:14px 0 22px}.progress-bar{background:linear-gradient(90deg,#5b6cff,#8068e9)}
.stage-line{display:grid;grid-template-columns:repeat(8,minmax(74px,1fr));overflow:visible;padding:0}.stage-pill{position:relative;border:0;background:transparent;padding:28px 3px 0;text-align:center;color:#8490a4;font-size:10px;font-weight:700;overflow:visible}.stage-pill:before{content:"";position:absolute;top:4px;left:50%;width:13px;height:13px;border-radius:50%;transform:translateX(-50%);background:#d5dde9;border:4px solid rgba(255,255,255,.82);box-shadow:0 0 0 1px rgba(126,145,177,.18);z-index:2}.stage-pill:after{content:"";position:absolute;top:13px;left:-50%;width:100%;height:2px;background:#d8e0eb;z-index:1}.stage-pill:first-child:after{display:none}.stage-pill.done,.stage-pill.current{background:transparent;border:0;color:#4f5fcf}.stage-pill.done:before{background:#6575df;box-shadow:0 0 0 1px rgba(91,108,255,.26)}.stage-pill.done:after,.stage-pill.current:after{background:#7380dc}.stage-pill.current:before{background:#5b6cff;box-shadow:0 0 0 5px rgba(91,108,255,.12),0 0 0 1px rgba(91,108,255,.3);animation:softPulse 1.8s ease-out infinite}
.status-message{text-align:center;margin-top:15px;color:#657187}
.result-wrap{animation:fadeReveal .3s ease-out}.summary-grid{gap:12px}.metric{position:relative;overflow:hidden;padding:17px 18px;border-radius:16px;transition:transform .2s ease-out,box-shadow .2s ease-out}.metric:hover{transform:translateY(-2px);box-shadow:0 20px 44px rgba(65,84,125,.15),inset 0 1px 0 #fff}.metric:after{content:"";position:absolute;right:-22px;top:-27px;width:70px;height:70px;border-radius:50%;background:rgba(91,108,255,.06)}.metric .value{font-size:28px}.metric .label{font-size:11px}
.toolbar{margin:18px 0 14px}.tabs{background:rgba(103,121,154,.10);border:1px solid rgba(255,255,255,.48);border-radius:13px}.tab{padding:9px 12px;transition:.2s ease-out}.tab.active{background:rgba(255,255,255,.76);color:#4250bd;box-shadow:0 5px 14px rgba(48,62,93,.08),inset 0 1px 0 #fff}
.tab-panel.active{animation:fadeReveal .25s ease-out}.case-card{border-radius:16px;margin-bottom:12px;transition:transform .2s ease-out}.case-card:hover{transform:translateY(-1px)}.case-head{padding:15px 16px}.case-title{font-size:14px}.case-body{background:rgba(249,251,254,.42);border-top-color:rgba(255,255,255,.66);padding:14px 16px}.steps{font-size:11px}.steps th{padding:8px;color:#566278}.steps td{padding:9px 8px;border-color:rgba(135,152,182,.14)}
.req-table{background:rgba(255,255,255,.30);border-color:rgba(255,255,255,.7);border-radius:15px}.req-table th{background:rgba(244,248,253,.58);border-color:rgba(255,255,255,.65);padding:11px}.req-table td{padding:12px 11px;border-color:rgba(133,151,181,.16)}
.review-layout{grid-template-columns:240px 1fr;gap:14px}.score-card{background:rgba(255,255,255,.46);border-radius:17px}.score-ring:after{background:rgba(245,248,252,.94)}.review-block{border-radius:16px}.context-card{background:rgba(255,255,255,.34);border-color:rgba(255,255,255,.65);border-radius:12px}.context-card summary{cursor:pointer;font-weight:750;color:#4d5a70}.context-body{padding-top:8px;white-space:pre-wrap;color:#5f6c80}
.exec-case{border-radius:15px;padding:14px}.failure{border:1px solid rgba(229,72,77,.18);border-left:3px solid #e5484d;background:rgba(255,240,241,.68);border-radius:12px;padding:13px}.raw-card pre{background:#172033}
.toast{border:1px solid rgba(255,255,255,.2);backdrop-filter:blur(16px)}
@keyframes fadeReveal{from{opacity:0;transform:translateY(6px);filter:blur(3px)}to{opacity:1;transform:none;filter:blur(0)}}
@keyframes softPulse{50%{box-shadow:0 0 0 8px rgba(91,108,255,.04),0 0 0 1px rgba(91,108,255,.3)}}
@media(max-width:1199px){.sidebar{width:222px}.main{margin-left:246px}.content{padding-left:22px;padding-right:22px}.topbar{padding-left:22px;padding-right:22px}.hero{padding:32px}.workbench{grid-template-columns:minmax(0,1.4fr) minmax(320px,.8fr)}}
@media(max-width:899px){.shell{padding-top:82px}.sidebar{display:flex;position:fixed;inset:8px 10px auto;width:auto;height:66px;border-radius:19px;padding:8px 10px;flex-direction:row;align-items:center}.brand{padding:0 8px 0 0}.brand-mark{width:36px;height:36px}.brand-title,.brand-sub,.nav-label,.sidebar-bottom,.nav a span:last-child{display:none}.nav{display:flex;grid-auto-flow:column;gap:4px;margin-left:auto;overflow-x:auto}.nav a{padding:5px}.nav a:hover{transform:none}.nav a.active:before{display:none}.nav-icon{width:34px;height:34px}.main{margin-left:0}.topbar{top:0;height:62px;padding:0 18px}.content{padding:4px 18px 60px}.workbench{grid-template-columns:1fr}.editor{border-right:0;border-bottom:1px solid rgba(255,255,255,.58)}.stage-line{overflow-x:auto;grid-template-columns:repeat(8,minmax(84px,1fr));padding-bottom:8px}.review-layout{grid-template-columns:1fr}.hero{min-height:240px}.hero:before{display:none}}
@media(max-width:599px){.shell{padding-top:74px}.sidebar{height:58px}.brand-mark{width:32px;height:32px;border-radius:10px}.nav-icon{width:30px;height:30px}.topbar{height:58px}.header-sub,.top-actions .mini{display:none}.health-pill{padding:7px 9px}.content{padding:2px 11px 48px}.hero{padding:24px 20px;min-height:0}.hero h1{font-size:29px}.hero p{font-size:13px}.flow{gap:5px}.flow-step{font-size:10px;padding:7px 9px}.flow-arrow{font-size:10px}.summary-grid,.exec-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.workbench .editor,.workbench .config{padding:17px}.toolbar{align-items:flex-start}.exports{width:100%}.review-layout{grid-template-columns:1fr}.case-body{overflow-x:auto}.steps{min-width:620px}.req-table{min-width:680px}.tab-panel{overflow-x:auto}.hero:after{opacity:.65}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*:before,*:after{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">R2</div>
      <div><div class="brand-title">Req2Test Agent</div><div class="brand-sub">AI Test Workbench</div></div>
    </div>
    <div class="nav-label">产品导航</div>
    <nav class="nav">
      <a class="active" href="#create"><span class="nav-icon">⌂</span><span>工作台</span></a>
      <a href="#create"><span class="nav-icon">＋</span><span>新建测试</span></a>
      <a href="#results" data-result-tab="cases"><span class="nav-icon">TC</span><span>测试用例</span></a>
      <a href="#results" data-result-tab="execution"><span class="nav-icon">▶</span><span>执行结果</span></a>
      <a href="#results" data-result-tab="review"><span class="nav-icon">R</span><span>RAG 知识库</span></a>
      <a href="#system"><span class="nav-icon">◉</span><span>系统状态</span></a>
    </nav>
    <div class="sidebar-bottom">
      <div class="service" id="system">
        <div class="service-row"><div><div class="service-title">平台服务</div><div class="service-meta" id="serviceMeta">正在检查...</div></div><span class="dot" id="serviceDot"></span></div>
      </div>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div><div class="header-title">Req2Test Agent</div><div class="header-sub">AI Test Design &amp; Execution Platform</div></div>
      <div class="top-actions">
        <span class="health-pill"><span class="dot" id="headerHealthDot"></span><span id="headerHealthText">System Checking</span></span>
        <a class="mini" href="https://github.com/xingqianyue268-alt/req2test-agent" target="_blank" rel="noreferrer">GitHub ↗</a>
      </div>
    </header>

    <div class="content">
      <section class="hero">
        <span class="eyebrow">✦ Unified AI Test Workspace</span>
        <h1>从需求到真实测试执行</h1>
        <p class="hero-en">AI-powered Test Design &amp; Execution Workspace</p>
        <p>将需求理解、RAG 检索、结构化用例设计、质量评审与真实执行整合在同一条可追溯链路中。</p>
        <div class="flow">
          <span class="flow-step">需求输入</span><span class="flow-arrow">→</span>
          <span class="flow-step">RAG</span><span class="flow-arrow">→</span>
          <span class="flow-step">AI 生成与评审</span><span class="flow-arrow">→</span>
          <span class="flow-step">自动执行</span><span class="flow-arrow">→</span>
          <span class="flow-step">失败归因</span>
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
            <div class="execution-tools" id="executionTools"><div class="tool-token"><span>H</span>HTTP Tool</div><div class="tool-token"><span>P</span>Pytest Runner</div></div>

            <details class="advanced">
              <summary>高级设置 · LLM 与运行参数</summary>
              <div class="advanced-body">
                <div class="field"><label for="mode">运行模式</label><select class="select" id="mode"><option value="demo">离线演示模式</option><option value="openai_compatible">OpenAI 兼容接口</option></select></div>
                <div id="modelFields" style="display:none">
                  <div class="two"><div class="field"><label for="model">模型</label><input id="model" type="text" value="gpt-4.1-mini"></div><div class="field"><label for="apiKey">API Key</label><input id="apiKey" type="password" placeholder="仅本次任务使用"></div></div>
                  <div class="field"><label for="llmBaseUrl">模型 Base URL</label><input id="llmBaseUrl" type="text" value="https://api.openai.com/v1"></div>
                </div>
              </div>
            </details>
            <button class="primary-btn" id="submitBtn" onclick="submitTask()">✦ AI 生成测试</button>
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
                <button class="tab" data-tab="review" onclick="switchTab('review',this)">AI 评审 &amp; RAG</button>
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
const STAGES=[
  {key:'queued',label:'Queued',aliases:['queued','started']},
  {key:'retrieval',label:'RAG',aliases:['retrieval']},
  {key:'analysis',label:'Analysis',aliases:['analysis']},
  {key:'design',label:'Test Design',aliases:['design','revision']},
  {key:'review',label:'Review',aliases:['review','generation_completed']},
  {key:'execution',label:'Execution',aliases:['tool_planning','http_execution','pytest_execution']},
  {key:'failure_analysis',label:'Failure Analysis',aliases:['failure_analysis']},
  {key:'completed',label:'Completed',aliases:['completed']}
];
let currentResult=null;
let currentTaskId='';

function esc(value){return String(value??'').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]))}
function toast(message,error=false){const el=document.getElementById('toast');el.textContent=message;el.className='toast show'+(error?' error':'');setTimeout(()=>el.className='toast',2600)}
function updateChars(){document.getElementById('charCount').textContent=document.getElementById('req').value.length+' 字符'}
function setExecution(enabled){document.getElementById('execute').checked=enabled;document.getElementById('baseUrlField').style.display=enabled?'block':'none';document.getElementById('executionTools').style.display=enabled?'grid':'none';document.getElementById('submitBtn').textContent=enabled?'✦ AI 生成并执行测试':'✦ AI 生成测试';document.getElementById('submitNote').textContent=enabled?'对显式 API 契约继续执行 HTTP Tool 与 Pytest':'生成完成后可查看用例、需求拆分、评审与 RAG 依据'}
function loadBusinessDemo(){document.getElementById('req').value=BUSINESS_DEMO;setExecution(false);updateChars();location.hash='#create'}
function loadPassDemo(){document.getElementById('req').value=PASS_DEMO;setExecution(true);updateChars();location.hash='#create'}
function loadFailDemo(){document.getElementById('req').value=FAIL_DEMO;setExecution(true);updateChars();location.hash='#create'}

function renderStages(stage){
  let currentIndex=STAGES.findIndex(item=>item.aliases.includes(stage));
  if(currentIndex<0)currentIndex=0;
  document.getElementById('stageLine').innerHTML=STAGES.map((item,i)=>`<span class="stage-pill ${i<currentIndex?'done':i===currentIndex?'current':''}">${esc(item.label)}</span>`).join('');
}
renderStages('queued');

async function checkHealth(){
  try{const r=await fetch('/health');const d=await r.json();if(r.ok&&d.status==='ok'){document.getElementById('serviceDot').classList.add('ok');document.getElementById('headerHealthDot').classList.add('ok');document.getElementById('serviceMeta').textContent='API 在线 · '+(d.task_store||'store');document.getElementById('headerHealthText').textContent='System Healthy'}}catch(e){document.getElementById('serviceMeta').textContent='连接失败';document.getElementById('headerHealthText').textContent='System Offline'}
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
  const review=result.review||{},contexts=result.retrieved_context||[],issues=review.issues||[],suggestions=review.suggestions||[],score=Number(review.score||0);document.getElementById('panel-review').innerHTML=`<div class="review-layout"><div class="score-card"><div class="score-ring" style="--score:${Math.max(0,Math.min(score,100))}"><span class="score-num">${esc(review.score??'-')}</span></div><div class="score-label">质量评审得分</div><div style="font-size:11px;margin-top:9px;color:#475467">覆盖率 ${review.coverage_rate!=null?Math.round(review.coverage_rate*100)+'%':'-'}</div></div><div><div class="review-block"><h4>评审问题</h4>${issues.length?issues.map(i=>`<div class="bullet">• ${esc(i)}</div>`).join(''):'<div class="bullet">✓ 未发现结构性问题</div>'}${suggestions.length?'<h4 style="margin-top:11px">改进建议</h4>'+suggestions.map(i=>`<div class="bullet">• ${esc(i)}</div>`).join(''):''}</div><div class="review-block"><h4>RAG 检索依据 <span class="subtle">${contexts.length} 条</span></h4>${contexts.length?contexts.map((c,i)=>`<details class="context-card" ${i===0?'open':''}><summary>Context ${i+1}</summary><div class="context-body">${esc(c)}</div></details>`).join(''):'<div class="bullet">本次未返回检索上下文</div>'}</div></div></div>`
}
function renderExecution(execution){
  const panel=document.getElementById('panel-execution');if(!execution||!execution.enabled){panel.innerHTML='<div class="empty">本次任务仅完成测试设计与评审。需要真实执行时，请在新建任务中开启“同时执行可执行 API 测试”。</div>';return}
  const summary=execution.summary||{},results=execution.http_results||[],failures=execution.failure_analysis||[],pytest=execution.pytest_result;panel.innerHTML=`<div class="exec-grid"><div class="metric"><div class="value">${esc(summary.total_http_cases??results.length)}</div><div class="label">HTTP 用例</div></div><div class="metric"><div class="value">${esc(summary.passed_http_cases??0)}</div><div class="label">HTTP 通过</div></div><div class="metric"><div class="value">${esc(summary.failed_http_cases??0)}</div><div class="label">HTTP 失败</div></div><div class="metric"><div class="value">${pytest?`<span class="badge ${pytest.passed?'pass':'fail'}">${pytest.passed?'PASS':'FAIL'}</span>`:'<span class="badge skip">SKIP</span>'}</div><div class="label">Pytest</div></div></div>${results.map(item=>`<div class="exec-case"><div class="exec-head"><div><div class="exec-title">${esc(item.method)} ${esc(pathname(item.url))}</div><div class="exec-meta">${esc(item.case_id)} · ${esc(item.duration_ms??'-')} ms · expected ${esc(item.expected_status)} / actual ${esc(item.status_code??'-')}</div></div><span class="badge ${item.passed?'pass':'fail'}">${item.passed?'PASS':'FAIL'}</span></div>${item.failures&&item.failures.length?`<div class="exec-meta" style="margin-top:8px">${esc(item.failures.join('；'))}</div>`:''}</div>`).join('')}${failures.length?'<h3 style="font-size:13px;margin:16px 0 8px">失败归因</h3>'+failures.map(f=>`<div class="failure"><strong>${esc(f.case_id)} · ${esc(f.category)}</strong><div>${esc(f.probable_cause)}</div><div>证据：${esc((f.evidence||[]).join('；')||'-')}</div><div>建议：${esc(f.suggestion||'-')}</div></div>`).join(''):''}`
}
function pathname(url){try{return new URL(url).pathname}catch(e){return url||'-'}}
function switchTab(name,button){document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab-panel').forEach(x=>x.classList.remove('active'));button.classList.add('active');document.getElementById('panel-'+name).classList.add('active')}

document.querySelectorAll('[data-result-tab]').forEach(link=>link.addEventListener('click',()=>{const name=link.dataset.resultTab;const button=document.querySelector(`.tab[data-tab="${name}"]`);if(button)switchTab(name,button)}));
document.querySelectorAll('.nav a').forEach(link=>link.addEventListener('click',()=>{document.querySelectorAll('.nav a').forEach(item=>item.classList.remove('active'));link.classList.add('active')}));

function downloadBlob(text,type,name){const blob=new Blob([text],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),500)}
function csvCell(v){const s=String(v??'').replace(/"/g,'""');return `"${s}"`}
function toMarkdown(result){let out='# Req2Test 测试结果\n\n';out+=`- 需求项：${(result.requirements||[]).length}\n- 测试用例：${(result.test_cases||[]).length}\n- 评审得分：${result.review?.score??'-'}\n- 覆盖率：${result.review?.coverage_rate!=null?Math.round(result.review.coverage_rate*100)+'%':'-'}\n\n`;for(const c of result.test_cases||[]){out+=`## ${c.case_id} ${c.title}\n\n- 模块：${c.module||'-'}\n- 优先级：${c.priority||'-'}\n- 类型：${c.test_type||'-'}\n- 来源需求：${c.source_requirement||'-'}\n\n| 序号 | 输入/操作描述 | 预期结果 |\n|---|---|---|\n`;for(const s of c.steps||[])out+=`| ${s.order} | ${String(s.action||'').replace(/\|/g,'\\|')} | ${String(s.expected||'').replace(/\|/g,'\\|')} |\n`;out+='\n'}return out}
function toCsv(result){const rows=[['用例编号','模块','用例名称','优先级','测试类型','来源需求','步骤序号','输入/操作描述','预期结果']];for(const c of result.test_cases||[]){for(const s of c.steps||[])rows.push([c.case_id,c.module,c.title,c.priority,c.test_type,c.source_requirement,s.order,s.action,s.expected])}return '\ufeff'+rows.map(r=>r.map(csvCell).join(',')).join('\n')}
function downloadResult(type){if(!currentResult){toast('暂无可导出结果',true);return}if(type==='json')downloadBlob(JSON.stringify(currentResult,null,2),'application/json','req2test_result.json');if(type==='md')downloadBlob(toMarkdown(currentResult),'text/markdown','req2test_cases.md');if(type==='csv')downloadBlob(toCsv(currentResult),'text/csv','req2test_cases.csv')}
</script>
</body>
</html>
"""
