"""fix mimo base_url drop /v1

修正 Xiaomi MiMo 供应商 base_url：去掉末尾 /v1（代码已拼 /v1/chat/completions）。

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-09-12 13:20:00

"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b0c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 需要修正的 provider → 正确的 base_url
FIXES = {
    "xiaomi-mimo": "https://api.xiaomimimo.com",
    "xiaomi-mimo-tp": "https://token-plan-cn.xiaomimimo.com",
}


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT provider_config FROM system_settings WHERE id = 1")
    )
    row = result.fetchone()
    if row is None or row[0] is None:
        return

    raw = row[0]
    configs = json.loads(raw) if isinstance(raw, str) else list(raw)

    changed = False
    for c in configs:
        key = c.get("provider")
        if key in FIXES:
            old_url = c.get("base_url", "")
            if old_url.endswith("/v1"):
                c["base_url"] = FIXES[key]
                changed = True

    if changed:
        conn.execute(
            sa.text("UPDATE system_settings SET provider_config = CAST(:val AS jsonb) WHERE id = 1"),
            {"val": json.dumps(configs, ensure_ascii=False)},
        )


def downgrade() -> None:
    # 加回 /v1（还原错误状态，仅回退用）
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT provider_config FROM system_settings WHERE id = 1")
    )
    row = result.fetchone()
    if row is None or row[0] is None:
        return

    raw = row[0]
    configs = json.loads(raw) if isinstance(raw, str) else list(raw)

    for c in configs:
        key = c.get("provider")
        if key in FIXES and not c.get("base_url", "").endswith("/v1"):
            c["base_url"] = c["base_url"] + "/v1"

    conn.execute(
        sa.text("UPDATE system_settings SET provider_config = CAST(:val AS jsonb) WHERE id = 1"),
        {"val": json.dumps(configs, ensure_ascii=False)},
    )
