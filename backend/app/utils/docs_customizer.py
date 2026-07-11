"""
自定义 Swagger UI 文档页面 — 语言选择 + 直接登录注入 token
"""
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html


def get_custom_swagger_html(openapi_url: str, lang: str = "en") -> HTMLResponse:
    """生成自定义 Swagger UI 页面，注入语言选择和登录表单"""
    html = get_swagger_ui_html(
        openapi_url=openapi_url,
        title="AI 群聊社交网络 - API 文档",
        swagger_ui_parameters={"displayLang": lang},
    ).body.decode()

    # 注入语言选择 + 快捷登录的 JavaScript
    inject_js = f"""
<script>
// ── 语言选择器 ──
(function() {{
    const currentLang = "{lang}";
    const container = document.querySelector('.topbar-wrapper') || document.querySelector('h2')?.parentElement;
    if (container) {{
        const langBar = document.createElement('div');
        langBar.style.cssText = 'display:flex;align-items:center;gap:8px;margin-left:auto;padding:8px 16px;';
        langBar.innerHTML = `
            <label style="color:#fff;font-size:13px;">🌐</label>
            <select id="lang-select" style="padding:4px 8px;border-radius:4px;border:1px solid #555;background:#333;color:#fff;font-size:13px;">
                <option value="en" ${{currentLang==='en'?'selected':''}}>English</option>
                <option value="zh" ${{currentLang==='zh'?'selected':''}}>中文</option>
            </select>
        `;
        container.after(langBar);
        document.getElementById('lang-select').addEventListener('change', function() {{
            window.location.search = '?lang=' + this.value;
        }});
    }}
}})();

// ── 快捷登录表单（注入到 Authorize 按钮附近）──
(function() {{
    // 查找 Authorize 按钮
    const observer = new MutationObserver(function() {{
        const authBtn = document.querySelector('.auth-wrapper button') || document.querySelector('[data-role="authorize-btn"]');
        const btn = authBtn || document.querySelector('button:has(.lock-icon)');
        if (!document.getElementById('quick-login-form')) {{
            addLoginForm();
        }
    }});
    observer.observe(document.body, {{ childList: true, subtree: true }});

    function addLoginForm() {{
        const target = document.querySelector('.auth-wrapper') || document.querySelector('.scheme-container');
        if (!target) return;

        const loginDiv = document.createElement('div');
        loginDiv.id = 'quick-login-form';
        loginDiv.style.cssText = 'margin:12px 0;padding:12px 16px;background:#f8f9fa;border-radius:6px;border:1px solid #d1d5db;';
        loginDiv.innerHTML = `
            <div style="font-weight:600;font-size:14px;margin-bottom:8px;color:#333;">🔑 快捷登录</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
                <div style="flex:1;min-width:140px;">
                    <label style="font-size:12px;color:#666;display:block;margin-bottom:2px;">账号</label>
                    <input id="ql-user" type="text" placeholder="用户名/邮箱" style="width:100%;padding:6px 10px;border:1px solid #ccc;border-radius:4px;font-size:13px;box-sizing:border-box;">
                </div>
                <div style="flex:1;min-width:140px;">
                    <label style="font-size:12px;color:#666;display:block;margin-bottom:2px;">密码</label>
                    <input id="ql-pass" type="password" placeholder="密码" style="width:100%;padding:6px 10px;border:1px solid #ccc;border-radius:4px;font-size:13px;box-sizing:border-box;">
                </div>
                <div>
                    <button id="ql-btn" style="padding:6px 20px;background:#1876d2;color:#fff;border:none;border-radius:4px;font-size:13px;cursor:pointer;white-space:nowrap;">登录并授权</button>
                </div>
            </div>
            <div id="ql-status" style="font-size:12px;margin-top:6px;color:#666;"></div>
        `;

        target.parentElement.insertBefore(loginDiv, target.nextSibling);

        document.getElementById('ql-btn').addEventListener('click', async function() {{
            const user = document.getElementById('ql-user').value.trim();
            const pass = document.getElementById('ql-pass').value;
            const status = document.getElementById('ql-status');

            if (!user || !pass) {{
                status.textContent = '⚠️ 请输入账号和密码';
                status.style.color = '#e53e3e';
                return;
            }}

            status.textContent = '⏳ 登录中...';
            status.style.color = '#666';
            document.getElementById('ql-btn').disabled = true;

            try {{
                const resp = await fetch('/auth/login', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ login_id: user, password: pass, method: 'direct' }}),
                }});
                const data = await resp.json();

                if (resp.ok && data.access_token) {{
                    // 注入 token 到 Swagger UI
                    if (window.ui && window.ui.authActions) {{
                        window.ui.authActions.authorize({{
                            "bearerAuth": {{
                                "name": "bearerAuth",
                                "schema": {{"type": "http","scheme": "bearer","bearerFormat": "JWT"}},
                                "value": data.access_token
                            }}
                        }});
                    }} else {{
                        // 备用：直接写入 localStorage（Swagger UI 会读取）
                        const key = 'authorized_' + btoa('bearerAuth');
                        try {{
                            const authData = JSON.parse(localStorage.getItem('swagger-ui-auth') || '{{}}');
                            authData.bearerAuth = {{ name: 'bearerAuth', schema: {{ type: 'http', scheme: 'bearer' }}, value: data.access_token }};
                            localStorage.setItem('swagger-ui-auth', JSON.stringify(authData));
                        }} catch(e) {{}}
                        // 刷新页面让授权生效
                        status.textContent = '✅ 登录成功！页面即将刷新...';
                        status.style.color = '#38a169';
                        setTimeout(() => location.reload(), 1000);
                        return;
                    }}
                    status.textContent = '✅ 登录成功，Token 已注入！';
                    status.style.color = '#38a169';
                }} else {{
                    status.textContent = '❌ 登录失败: ' + (data.detail || JSON.stringify(data));
                    status.style.color = '#e53e3e';
                }}
            }} catch (e) {{
                status.textContent = '❌ 请求失败: ' + e.message;
                status.style.color = '#e53e3e';
            }} finally {{
                document.getElementById('ql-btn').disabled = false;
            }}
        }});
    }}
}})();
</script>

<style>
  /* 暗色主题适配 */
  .dark-theme #quick-login-form {{
      background: #2d2d2d; border-color: #444;
  }}
  .dark-theme #quick-login-form > div:first-child {{ color: #e0e0e0 !important; }}
  .dark-theme #quick-login-form label {{ color: #aaa !important; }}
  .dark-theme #quick-login-form input {{
      background: #3d3d3d; border-color: #555; color: #e0e0e0;
  }}
</style>
"""
    html = html.replace("</body>", inject_js + "</body>")
    return HTMLResponse(content=html)
