"""
系统设置 Pydantic Schema
"""
from pydantic import BaseModel, Field


class SystemSettingsResponse(BaseModel):
    """系统设置（公开）"""
    id: int
    default_language: str
    default_platform_credit: int = 0
    default_file_quota_mb: int = 100
    default_concurrent_ai_limit: int = 3
    updated_by: int | None = None
    updated_at: str | None = None
    login_providers: list[str] = ["direct"]
    require_email_verification: bool = False


class UpdateSystemSettingsRequest(BaseModel):
    """管理后台更新系统设置"""
    default_language: str | None = Field(None, description="全局默认语言: zh 或 en")
    default_platform_credit: int | None = Field(None, ge=0, description="全局默认平台赠送额度")
    default_file_quota_mb: int | None = Field(None, ge=1, description="新用户默认文件配额（MB），修改后所有用户同步调整")
    default_concurrent_ai_limit: int | None = Field(None, ge=1, le=20, description="新建群聊默认 AI 并发数")


class SetupCompleteRequest(BaseModel):
    """完成初始化设置（最终步骤调用，标记向导完成）"""
    language: str | None = Field(None, description="用户选择的语言，留空保留当前设置")
    completed: bool = Field(True, description="标记向导完成")


class LanguageUpdateRequest(BaseModel):
    """更新用户语言（向导步骤1保存，不标记完成）"""
    language: str = Field(..., description="用户选择的语言: zh 或 en")


# ── v1.0.0 邮箱认证 ──

class SmtpConfigRequest(BaseModel):
    """SMTP 配置请求"""
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    username: str = Field(..., max_length=255)
    password: str | None = Field(None, description="留空保持现有密码不变")
    from_email: str = Field(..., max_length=255)
    from_name: str = Field("AIsChat", max_length=100)
    use_tls: bool = True


class AuthSettingsRequest(BaseModel):
    """认证设置请求"""
    require_email_verification: bool | None = Field(None)
    login_providers: list[str] | None = Field(None, min_length=1)


class AuthSettingsResponse(BaseModel):
    """认证设置完整响应（管理面板用）"""
    require_email_verification: bool = False
    login_providers: list[str] = ["direct"]
    smtp_configured: bool = False
    smtp_config: dict | None = None  # 密码已脱敏
    smtp_configs: list[dict] = []    # v1.0.0 多 SMTP（密码已脱敏）


# ── v1.0.0 多 SMTP 容灾 ──

class SmtpConfigItem(BaseModel):
    """单个 SMTP 配置项"""
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(587, ge=1, le=65535)
    username: str = Field("", max_length=255)
    password: str | None = Field(None, description="留空保持现网不变")
    from_email: str = Field(..., max_length=255)
    from_name: str = Field("AIsChat", max_length=100)
    use_tls: bool = True
    is_active: bool = True
    priority: int = Field(0, ge=0)


class SmtpConfigsRequest(BaseModel):
    """多 SMTP 配置批量保存请求"""
    configs: list[SmtpConfigItem] = Field(..., min_length=1)


class SmtpTestRequest(BaseModel):
    """测试单个 SMTP 配置"""
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(587, ge=1, le=65535)
    username: str = Field("", max_length=255)
    password: str | None = Field(None)
    from_email: str = Field(..., max_length=255)
    from_name: str = Field("AIsChat", max_length=100)
    use_tls: bool = True


# ── v1.0.0 自定义邮件模板 ──

class EmailTemplateItem(BaseModel):
    """单个邮件模板（subject + body_html）"""
    subject: str
    body_html: str


class EmailTemplatesData(BaseModel):
    """邮件模板数据（按语言 + 用途组织）"""
    zh: dict[str, EmailTemplateItem] = {}  # key: register/login/rebind
    en: dict[str, EmailTemplateItem] = {}


class EmailTemplatesRequest(BaseModel):
    """邮件模板保存请求"""
    templates: EmailTemplatesData
