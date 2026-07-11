"""
SMTP 邮件发送服务
使用 aiosmtplib 异步发送验证码邮件
v1.0.0: 多 SMTP 容灾 + 自定义邮件模板
"""
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.system_settings import SystemSettings
from app.services.system_settings_service import get_settings
from app.utils.crypto import decrypt_api_key, encrypt_api_key

logger = logging.getLogger(__name__)

# ── 邮件模板预设系统 ──
# 三版预设：gradient（渐变版，默认）、simple（简版）、custom（自定义版）
# {from_name} 和 {code} 用双花括号转义，留到发送时由 _send_with_config 替换

_TMPL_SIMPLE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{from_name}} - {purpose_label}</title>
</head>
<body style="margin:0;padding:0;background-color:#F4F4F7;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#F4F4F7;">
    <tr>
      <td align="center" style="padding:20px 10px;">
        <table role="presentation" cellpadding="0" cellspacing="0" width="480" style="max-width:480px;background-color:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.05);">
          <tr>
            <td style="background-color:#7C3AED;padding:24px 30px;border-radius:12px 12px 0 0;">
              <h1 style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:22px;color:#FFFFFF;font-weight:600;">{{from_name}}</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:30px 30px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:#333333;">
              <p style="margin:0 0 10px;">{greeting}</p>
              <p style="margin:0 0 20px;">{instruction}</p>
              <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:0 0 24px;">
                <tr>
                  <td style="background-color:#F3F4F6;border-radius:10px;padding:18px 10px;text-align:center;">
                    <span style="font-family:'Courier New',Courier,monospace;font-size:36px;font-weight:700;letter-spacing:8px;color:#1F2937;word-break:break-all;">{{code}}</span>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px;font-size:14px;color:#4B5563;">{validity}</p>
              {warning}
            </td>
          </tr>
          <tr>
            <td style="padding:0 30px 24px;border-top:1px solid #E5E7EB;padding-top:20px;">
              <p style="margin:0;font-size:12px;color:#9CA3AF;line-height:1.5;">{footer}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

_TMPL_GRADIENT = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{from_name}} - {purpose_label}</title>
</head>
<body style="margin:0;padding:0;background-color:#F4F4F7;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#F4F4F7;">
    <tr>
      <td align="center" style="padding:20px 10px;">
        <table role="presentation" cellpadding="0" cellspacing="0" width="480" style="max-width:480px;background-color:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.05);">
          <tr>
            <td style="background-color:#7C3AED;background-image:linear-gradient(135deg, #8B5CF6 0%, #4F46E5 100%);padding:28px 30px;border-radius:12px 12px 0 0;">
              <h1 style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:22px;color:#FFFFFF;font-weight:600;letter-spacing:0.5px;">{{from_name}}</h1>
            </td>
          </tr>
          <tr>
            <td style="background-color:#FFFFFF;background-image:linear-gradient(180deg, #FFFFFF 0%, #F3F0FA 100%);padding:30px 30px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:#333333;">
              <p style="margin:0 0 10px;">{greeting}</p>
              <p style="margin:0 0 20px;">{instruction}</p>
              <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:0 0 24px;">
                <tr>
                  <td style="background-color:#F3F4F6;background-image:linear-gradient(135deg, #F3E8FF 0%, #F3F4F6 100%);border-radius:10px;padding:18px 10px;text-align:center;">
                    <span style="font-family:'Courier New',Courier,monospace;font-size:36px;font-weight:700;letter-spacing:8px;color:#1F2937;word-break:break-all;user-select:all;-webkit-user-select:all;">{{code}}</span>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px;font-size:14px;color:#4B5563;">{validity}</p>
              {warning}
            </td>
          </tr>
          <tr>
            <td style="padding:0 30px 24px;border-top:1px solid #E5E7EB;padding-top:20px;background-color:#F3F0FA;">
              <p style="margin:0;font-size:12px;color:#9CA3AF;line-height:1.5;">{footer}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

_TMPL_DEFAULT = _TMPL_GRADIENT

# ── 语言内容占位符（zh/en，共享于所有预设） ──

_ZH = {
    "register": {
        "subject": "【{from_name}】邮箱验证码",
        "greeting": "你好，",
        "instruction": "你正在注册账号，请使用以下验证码完成验证：",
        "validity": "验证码 <strong style=\"color:#DC2626;\">5 分钟</strong> 内有效，请勿转发给他人。",
        "warning": '<p style="margin:0 0 20px;font-size:13px;color:#9CA3AF;">如果这不是你的操作，请忽略此邮件，无需回复。</p>',
        "footer": "此邮件由 <strong>{from_name}</strong> 系统自动发送，请勿回复。<br>如有疑问，请联系客服。",
    },
    "login": {
        "subject": "【{from_name}】登录验证码",
        "greeting": "你好，",
        "instruction": "你正在请求登录验证码，请使用以下验证码完成验证：",
        "validity": "验证码 <strong style=\"color:#DC2626;\">5 分钟</strong> 内有效，请勿转发给他人。",
        "warning": '<p style="margin:0 0 20px;font-size:13px;color:#9CA3AF;">如果这不是你的操作，请忽略此邮件，无需回复。</p>',
        "footer": "此邮件由 <strong>{from_name}</strong> 系统自动发送，请勿回复。<br>如有疑问，请联系客服。",
    },
    "rebind": {
        "subject": "【{from_name}】换绑邮箱验证码",
        "greeting": "你好，",
        "instruction": "你正在更换绑定邮箱，请使用以下验证码完成验证：",
        "validity": "验证码 <strong style=\"color:#DC2626;\">5 分钟</strong> 内有效，请勿转发给他人。",
        "warning": '<p style="margin:0 0 20px;font-size:13px;color:#9CA3AF;">如果这不是你的操作，你的账号可能已被盗用，请立即联系管理员。</p>',
        "footer": "此邮件由 <strong>{from_name}</strong> 系统自动发送，请勿回复。<br>如有疑问，请联系客服。",
    },
}

_EN = {
    "register": {
        "subject": "[{from_name}] Email Verification Code",
        "greeting": "Hello,",
        "instruction": "You are registering an account. Please use the following code to verify your email:",
        "validity": "This code is valid for <strong style=\"color:#DC2626;\">5 minutes</strong>. Do not share it with anyone.",
        "warning": '<p style="margin:0 0 20px;font-size:13px;color:#9CA3AF;">If this wasn\'t you, please ignore this email.</p>',
        "footer": "This email was sent automatically by <strong>{from_name}</strong>. Please do not reply.<br>For assistance, contact our support team.",
    },
    "login": {
        "subject": "[{from_name}] Login Verification Code",
        "greeting": "Hello,",
        "instruction": "You requested a login verification code. Please use the following code:",
        "validity": "This code is valid for <strong style=\"color:#DC2626;\">5 minutes</strong>. Do not share it with anyone.",
        "warning": '<p style="margin:0 0 20px;font-size:13px;color:#9CA3AF;">If this wasn\'t you, please ignore this email.</p>',
        "footer": "This email was sent automatically by <strong>{from_name}</strong>. Please do not reply.<br>For assistance, contact our support team.",
    },
    "rebind": {
        "subject": "[{from_name}] Email Rebind Verification Code",
        "greeting": "Hello,",
        "instruction": "You are changing your bound email address. Please use the following code to verify:",
        "validity": "This code is valid for <strong style=\"color:#DC2626;\">5 minutes</strong>. Do not share it with anyone.",
        "warning": '<p style="margin:0 0 20px;font-size:13px;color:#9CA3AF;">If this wasn\'t you, your account may have been compromised. Contact the admin immediately.</p>',
        "footer": "This email was sent automatically by <strong>{from_name}</strong>. Please do not reply.<br>For assistance, contact our support team.",
    },
}

_PURPOSE_LABELS_ZH = {"register": "邮箱验证", "login": "登录验证", "rebind": "换绑验证"}
_PURPOSE_LABELS_EN = {"register": "Email Verification", "login": "Login Verification", "rebind": "Email Rebind"}

def _build_preset(body_tmpl: str, lang: str, purposes: dict, labels: dict) -> dict:
    """用 body_tmpl + 语言内容构建一个完整预设的 {lang: {purpose: {subject, body_html}}}"""
    return {p: {
        "subject": purposes[p]["subject"],
        "body_html": body_tmpl.format(
            lang=lang,
            purpose_label=labels[p],
            greeting=purposes[p]["greeting"],
            instruction=purposes[p]["instruction"],
            validity=purposes[p]["validity"],
            warning=purposes[p]["warning"],
            footer=purposes[p]["footer"],
        ),
    } for p in purposes}

# 内置预设
_PRESET_TEMPLATES = {
    "simple": {
        "zh": _build_preset(_TMPL_SIMPLE, "zh-CN", _ZH, _PURPOSE_LABELS_ZH),
        "en": _build_preset(_TMPL_SIMPLE, "en", _EN, _PURPOSE_LABELS_EN),
    },
    "gradient": {
        "zh": _build_preset(_TMPL_GRADIENT, "zh-CN", _ZH, _PURPOSE_LABELS_ZH),
        "en": _build_preset(_TMPL_GRADIENT, "en", _EN, _PURPOSE_LABELS_EN),
    },
}

# 默认预设名
_DEFAULT_PRESET = "gradient"
# 兼容旧代码：直接暴露为 EMAIL_TEMPLATES
EMAIL_TEMPLATES = _PRESET_TEMPLATES[_DEFAULT_PRESET]


class SafeDict(dict):
    """安全字典：格式化时缺失的 key 保留原占位符，不抛 KeyError"""
    def __missing__(self, key):
        return '{' + key + '}'


async def _get_smtp_configs(db: AsyncSession) -> list[dict]:
    """读取全部 SMTP 配置列表（密码解密）。未配置返回空列表。

    兼容三种格式：
    1. 新格式 JSONB 数组: [{"host":..., "is_active":true, "priority":0}, ...]
    2. 旧格式 JSONB 单对象: {"host":..., ...} → 自动包装为数组
    3. JSON 字符串（历史遗留）
    """
    settings = await get_settings(db)
    smtp_raw = settings.get("smtp_config")

    if not smtp_raw:
        return []

    # 兼容 JSON 字符串
    if isinstance(smtp_raw, str):
        import json
        smtp_raw = json.loads(smtp_raw)

    # 兼容旧格式：单对象 → 包装为数组
    if isinstance(smtp_raw, dict):
        smtp_raw = [smtp_raw]

    if not isinstance(smtp_raw, list):
        return []

    result = []
    for cfg in smtp_raw:
        if not isinstance(cfg, dict):
            continue
        cfg = dict(cfg)  # 浅拷贝，避免修改 DB 中的原始值
        # 解密密码
        if cfg.get("password_encrypted"):
            try:
                cfg["password"] = decrypt_api_key(cfg.pop("password_encrypted"))
            except Exception:
                cfg["password"] = ""
        else:
            cfg["password"] = cfg.get("password", "")
        # 确保兼容字段存在
        cfg.setdefault("is_active", True)
        cfg.setdefault("priority", 0)
        result.append(cfg)

    return result


def _pick_smtp_config(configs: list[dict]) -> dict | None:
    """按 priority 升序，取第一个 is_active=true 的配置。无可用返回 None。"""
    active = [c for c in configs if c.get("is_active", True)]
    if not active:
        return None
    active.sort(key=lambda c: c.get("priority", 0))
    return active[0]


async def get_email_templates(db: AsyncSession) -> dict:
    """获取当前生效的邮件模板（按 preset 选择）"""
    settings = await get_settings(db)
    raw = settings.get("email_templates")
    preset = _DEFAULT_PRESET
    custom_templates = None

    if raw and isinstance(raw, dict):
        preset = raw.get("preset", _DEFAULT_PRESET)
        if preset == "custom":
            custom_templates = {k: v for k, v in raw.items() if k in ("zh", "en")}

    if preset == "custom" and custom_templates and (custom_templates.get("zh") or custom_templates.get("en")):
        return custom_templates

    preset_tmpl = _PRESET_TEMPLATES.get(preset)
    if preset_tmpl:
        return preset_tmpl
    return _PRESET_TEMPLATES[_DEFAULT_PRESET]


async def get_email_template_preset(db: AsyncSession) -> str:
    """获取当前邮件模板预设名"""
    settings = await get_settings(db)
    raw = settings.get("email_templates")
    if raw and isinstance(raw, dict):
        return raw.get("preset", _DEFAULT_PRESET)
    return _DEFAULT_PRESET


async def set_email_template_preset(db: AsyncSession, preset: str, custom_templates: dict | None = None):
    """设置邮件模板预设（gradient/simple/custom）"""
    if preset not in ("gradient", "simple", "custom"):
        raise ValueError(f"无效预设: {preset}")
    settings = await get_settings(db)
    raw = (settings.get("email_templates") or {}).copy()
    if isinstance(raw, str):
        import json
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raw = {}
    raw["preset"] = preset
    if preset == "custom" and custom_templates:
        raw["zh"] = custom_templates.get("zh", {})
        raw["en"] = custom_templates.get("en", {})
    elif preset != "custom":
        raw.pop("zh", None)
        raw.pop("en", None)
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    row = result.scalar_one_or_none()
    if row:
        row.email_templates = raw


def format_email_template(tpl: dict, vars: dict) -> dict:
    """安全格式化单个模板，变量缺失时保留原占位符（不抛异常）"""
    sd = SafeDict(vars)
    return {
        "subject": tpl["subject"].format_map(sd),
        "body_html": tpl["body_html"].format_map(sd),
    }


def format_all_templates(templates: dict, vars: dict) -> dict:
    """安全格式化全部模板（zh + en 全部 purpose）"""
    sd = SafeDict(vars)
    result = {}
    for lang in templates:
        result[lang] = {}
        for purpose, tpl in templates[lang].items():
            result[lang][purpose] = {
                "subject": tpl["subject"].format_map(sd),
                "body_html": tpl["body_html"].format_map(sd),
            }
    return result


async def _send_with_config(cfg: dict, to_email: str, code: str, template: dict):
    """使用指定 SMTP 配置发送单封邮件。成功返回 True，失败抛异常。"""
    from_name = cfg.get("from_name", "AIsChat")
    sd = SafeDict(code=code, from_name=from_name)

    subject = template["subject"].format_map(sd)
    body_html = template["body_html"].format_map(sd)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{cfg['from_email']}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    import aiosmtplib
    await aiosmtplib.send(
        msg,
        hostname=cfg["host"],
        port=cfg.get("port", 587),
        username=cfg["username"],
        password=cfg["password"],
        use_tls=cfg.get("use_tls", True),
    )


async def send_verification_code_email(
    db: AsyncSession,
    to_email: str,
    code: str,
    purpose: str,
    lang: str = "zh",
) -> bool:
    """发送验证码邮件（多 SMTP 容灾）。

    按优先级遍历全部 SMTP 配置，遇失败自动尝试下一个。
    成功返回 True，全部失败抛 ValueError（包含每个配置的错误信息）。
    """
    configs = await _get_smtp_configs(db)
    if not configs:
        raise ValueError("邮件服务未配置，请联系管理员")

    templates = await get_email_templates(db)
    lang = lang if lang in templates else "zh"
    template = templates[lang].get(purpose, templates[lang].get("register", templates[lang]["register"]))

    # 按优先级排序
    sorted_configs = sorted(configs, key=lambda c: c.get("priority", 0))

    errors = []
    tried = 0
    for i, cfg in enumerate(sorted_configs):
        if not cfg.get("is_active", True):
            continue
        tried += 1
        try:
            await _send_with_config(cfg, to_email, code, template)
            logger.info(f"验证码邮件已发送至 {to_email} (purpose={purpose}, smtp=#{i} {cfg.get('host')})")
            return True
        except Exception as e:
            err_msg = f"SMTP #{i} ({cfg.get('host')}): {e}"
            logger.warning(f"发送验证码邮件失败 ({err_msg})，尝试下一个配置...")
            errors.append(err_msg)

    if tried == 0:
        raise ValueError("没有可用的 SMTP 配置（全部已停用）")
    raise ValueError(f"所有 SMTP 配置均发送失败 ({tried} 个尝试): {'; '.join(errors)}")


async def test_smtp_connection(config: dict) -> tuple[bool, str]:
    """测试 SMTP 连接。返回 (ok, message)。"""
    try:
        import aiosmtplib
        from email.mime.text import MIMEText

        test_msg = MIMEText("AIsChat SMTP connection test", "plain", "utf-8")
        test_msg["Subject"] = "AIsChat SMTP Test"
        test_msg["From"] = f"{config.get('from_name', 'Test')} <{config['from_email']}>"
        test_msg["To"] = config["from_email"]  # 发给发件人自己

        await aiosmtplib.send(
            test_msg,
            hostname=config["host"],
            port=config.get("port", 587),
            username=config.get("username"),
            password=config.get("password", ""),
            use_tls=config.get("use_tls", True),
        )
        return True, "SMTP 连接成功，测试邮件已发送"
    except Exception as e:
        return False, f"SMTP 连接失败: {e}"
