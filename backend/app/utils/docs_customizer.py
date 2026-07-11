"""
自定义 Swagger UI 文档页面 — 语言选择 + 直接登录注入 token
"""
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html


def get_custom_swagger_html(openapi_url: str, lang: str = "en") -> HTMLResponse:
    """生成自定义 Swagger UI 页面，注入语言选择和登录表单"""
    # Swagger UI locale 映射
    locale_map = {"en": "en", "zh": "zh-CN"}
    swagger_lang = locale_map.get(lang, "en")

    html = get_swagger_ui_html(
        openapi_url=openapi_url,
        title="AI 群聊社交网络 - API 文档",
        swagger_ui_parameters={"displayLang": swagger_lang},
    ).body.decode()

    # JS 用普通字符串（避免 f-string 的 {} 与 JS 语法冲突）
    inject_js = """
<style>
#ql-bar {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 20px; background: #1a1a2e; color: #eee;
    font-size: 14px; border-bottom: 1px solid #333;
    flex-wrap: wrap;
}
#ql-bar .ql-title { font-weight: 600; margin-right: 8px; }
#ql-bar select {
    padding: 4px 8px; border-radius: 4px; border: 1px solid #555;
    background: #2d2d2d; color: #eee; font-size: 13px;
}
#ql-bar .ql-input {
    padding: 5px 10px; border: 1px solid #555; border-radius: 4px;
    background: #2d2d2d; color: #eee; font-size: 13px; width: 140px;
}
#ql-bar .ql-btn {
    padding: 5px 16px; background: #1876d2; color: #fff;
    border: none; border-radius: 4px; font-size: 13px; cursor: pointer;
    white-space: nowrap;
}
#ql-bar .ql-btn:hover { background: #1565c0; }
#ql-bar .ql-btn:disabled { opacity: 0.6; cursor: not-allowed; }
#ql-bar .ql-status { font-size: 12px; }
#ql-bar .ql-sep { width: 1px; height: 24px; background: #444; }
</style>

<div id="ql-bar">
    <span class="ql-title">LANG_TITLE</span>
    <select id="ql-lang">
        <option value="en">English</option>
        <option value="zh">中文</option>
    </select>
    <span class="ql-sep"></span>
    <span>LANG_LOGIN</span>
    <input class="ql-input" id="ql-user" type="text" placeholder="LANG_USER">
    <input class="ql-input" id="ql-pass" type="password" placeholder="LANG_PASS">
    <button class="ql-btn" id="ql-btn">LANG_BTN</button>
    <span class="ql-status" id="ql-status"></span>
</div>

<script>
(function() {
    var LANG = 'LANG_SEL';

    // 语言选项
    document.getElementById('ql-lang').value = LANG;
    document.getElementById('ql-lang').addEventListener('change', function() {
        window.location.search = '?lang=' + this.value;
    });

    // 快捷登录
    document.getElementById('ql-btn').addEventListener('click', async function() {
        var user = document.getElementById('ql-user').value.trim();
        var pass = document.getElementById('ql-pass').value;
        var status = document.getElementById('ql-status');
        var btn = document.getElementById('ql-btn');

        if (!user || !pass) {
            status.textContent = (LANG==='zh' ? '请输入账号和密码' : 'Enter username & password');
            status.style.color = '#e53e3e'; return;
        }
        status.textContent = (LANG==='zh' ? '登录中...' : 'Logging in...');
        status.style.color = '#aaa';
        btn.disabled = true;

        try {
            var resp = await fetch('/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({login_id: user, password: pass, method: 'direct'})
            });
            var data = await resp.json();
            if (resp.ok && data.access_token) {
                // 尝试注入到 Swagger UI
                if (window.ui && window.ui.authActions) {
                    window.ui.authActions.authorize({
                        "bearerAuth": {
                            "name": "bearerAuth",
                            "schema": {"type": "http","scheme": "bearer","bearerFormat": "JWT"},
                            "value": data.access_token
                        }
                    });
                }
                // 备用：保存到 localStorage
                try {
                    var authData = JSON.parse(localStorage.getItem('swagger-ui-auth') || '{}');
                    authData.bearerAuth = {name:'bearerAuth',schema:{type:'http',scheme:'bearer'},value:data.access_token};
                    localStorage.setItem('swagger-ui-auth', JSON.stringify(authData));
                } catch(e) {}
                status.textContent = (LANG==='zh' ? '登录成功！' : 'Login success!');
                status.style.color = '#38a169';
                setTimeout(function(){location.reload()}, 800);
            } else {
                status.textContent = (LANG==='zh' ? '失败: ' : 'Failed: ') + (data.detail || '?');
                status.style.color = '#e53e3e';
            }
        } catch(e) {
            status.textContent = (LANG==='zh' ? '请求失败: ' : 'Error: ') + e.message;
            status.style.color = '#e53e3e';
        } finally {
            btn.disabled = false;
        }
    });
})();
</script>
""".replace("LANG_TITLE", "🌐 Language" if lang == "en" else "🌐 语言")\
    .replace("LANG_LOGIN", "🔑 Login" if lang == "en" else "🔑 登录")\
    .replace("LANG_USER", "username" if lang == "en" else "用户名")\
    .replace("LANG_PASS", "password" if lang == "en" else "密码")\
    .replace("LANG_BTN", "Authorize" if lang == "en" else "授权")\
    .replace("LANG_SEL", lang)

    # 插入到 body 开头
    html = html.replace("<body>", "<body>" + inject_js)
    return HTMLResponse(content=html)
