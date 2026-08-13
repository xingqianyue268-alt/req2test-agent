"""Editorial login and registration pages for the vanilla browser application."""

from __future__ import annotations


def render_auth_html(mode: str) -> str:
    register = mode == "register"
    title = "CREATE\nACCOUNT." if register else "WELCOME\nBACK."
    action = "创建账户" if register else "登录"
    alternate_href = "/login" if register else "/register"
    alternate = "返回登录" if register else "注册账户"
    confirm = (
        '<label>确认密码</label>'
        '<input id="confirm" type="password" autocomplete="new-password" '
        'minlength="8" maxlength="128" required>'
        if register
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Req2Test · {'Register' if register else 'Login'}</title>
<style>
:root{{--paper:#f3f4f2;--blue-paper:#eef2f5;--ink:#12171f;--muted:#68717d;--blue:#5f7fa8;--line:rgba(18,23,31,.12);--display:Inter,-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;--zh:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;min-width:320px;min-height:100vh;background:var(--paper);color:var(--ink);font-family:var(--display);-webkit-font-smoothing:antialiased}}a{{color:inherit;text-decoration:none}}.shell{{min-height:100vh;display:grid;grid-template-rows:auto 1fr}}header{{height:76px;display:flex;align-items:center;justify-content:space-between;width:min(calc(100% - 72px),1400px);margin:auto;border-bottom:1px solid var(--line)}}.brand{{font-size:16px;font-weight:850;letter-spacing:.12em}}.brand b{{color:var(--blue)}}.system{{font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--muted)}}main{{width:min(calc(100% - 72px),1400px);margin:auto;display:grid;grid-template-columns:1.25fr .75fr;gap:9vw;align-items:center;padding:60px 0 90px}}.kicker{{font-size:11px;font-weight:750;letter-spacing:.17em;color:var(--muted)}}h1{{margin:25px 0 0;font-size:clamp(72px,8vw,118px);font-weight:500;line-height:.82;letter-spacing:-.065em;white-space:pre-line}}h1::first-line{{color:var(--ink)}}.intro{{max-width:500px;margin-top:34px;padding-top:20px;border-top:1px solid var(--line);font-family:var(--zh);color:var(--muted);font-size:15px;line-height:1.75}}form{{padding:30px 0;border-top:1px solid var(--ink);border-bottom:1px solid var(--line)}}.field{{margin-bottom:25px}}label{{display:flex;justify-content:space-between;margin-bottom:10px;font-size:12px;font-weight:750;letter-spacing:.08em}}label span{{font-family:var(--zh);font-size:12px;color:var(--muted);letter-spacing:0}}input{{width:100%;padding:15px 2px;border:0;border-bottom:1px solid var(--line);border-radius:0;background:transparent;outline:0;font-size:17px}}input:focus{{border-color:var(--blue)}}button{{width:100%;display:flex;justify-content:space-between;margin-top:34px;padding:17px 19px;border:0;background:#0f1823;color:#fff;font-size:13px;font-weight:800;letter-spacing:.09em;cursor:pointer}}button:hover{{background:#26384b}}button:disabled{{opacity:.55}}.alternate{{display:inline-block;margin-top:25px;padding-bottom:8px;border-bottom:1px solid var(--line);font-size:12px;font-weight:750;letter-spacing:.06em}}.message{{min-height:22px;margin-top:18px;color:#a84f52;font-family:var(--zh);font-size:13px}}@media(max-width:800px){{header,main{{width:calc(100% - 36px)}}main{{grid-template-columns:1fr;align-items:start;padding-top:70px}}h1{{font-size:clamp(62px,17vw,96px)}}}}
</style></head><body><div class="shell"><header><a class="brand" href="/workflow">REQ<b>2</b>TEST</a><span class="system">安全访问</span></header><main><section><div class="kicker">AI TEST DESIGN &amp; EXECUTION PLATFORM</div><h1>{title}</h1><p class="intro">登录统一测试工作台，将需求理解、RAG 检索、测试设计、AI 评审与真实执行保存在你的专属任务空间。</p></section><section><form id="authForm"><div class="field"><label>邮箱</label><input id="email" type="email" autocomplete="email" maxlength="255" required></div><div class="field"><label>密码</label><input id="password" type="password" autocomplete="{'new-password' if register else 'current-password'}" minlength="8" maxlength="128" required></div>{confirm}<button id="submit" type="submit"><span>{action}</span><span>→</span></button><div class="message" id="message"></div></form><a class="alternate" href="{alternate_href}">{alternate}</a></section></main></div>
<script>
const REGISTER={str(register).lower()};
function safeNext(){{const value=new URLSearchParams(location.search).get('next');return value&&value.startsWith('/')&&!value.startsWith('//')?value:'/workbench'}}
document.getElementById('authForm').addEventListener('submit',async event=>{{event.preventDefault();const button=document.getElementById('submit'),message=document.getElementById('message'),email=document.getElementById('email').value.trim(),password=document.getElementById('password').value;message.textContent='';if(REGISTER&&password!==document.getElementById('confirm').value){{message.textContent='两次输入的密码不一致';return}}button.disabled=true;try{{if(REGISTER){{const register=await fetch('/api/v1/auth/register',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email,password}})}});const detail=await register.json();if(!register.ok)throw new Error(detail.detail||'注册失败')}}const login=await fetch('/api/v1/auth/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email,password}})}});const detail=await login.json();if(!login.ok)throw new Error(detail.detail||'登录失败');location.replace(safeNext())}}catch(error){{message.textContent=error.message||'认证失败';button.disabled=false}}}});
</script></body></html>"""
