"""add xiaomi mimo provider presets

在 provider_config 中追加 Xiaomi MiMo 供应商预设（按量付费 + Token Plan）。

Revision ID: b0c1d2e3f4a5
Revises: a9b8c7d6e5f4
Create Date: 2026-09-12 13:00:00

"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b0c1d2e3f4a5'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIMO_PRESETS = [
    {
        "name": "Xiaomi MiMo",
        "provider": "xiaomi-mimo",
        "base_url": "https://api.xiaomimimo.com/v1",
        "chat_model": "mimo-v2.5",
        "work_model": "mimo-v2.5-pro",
        "embedding_model": "",
        "thinking_supported": True,
        "api_key_url": "https://platform.xiaomimimo.com/#/console/api-keys",
        "is_default": False,
        "model_options": [
            {"value": "mimo-v2.5", "label": "MiMo V2.5（多模态，推荐）"},
            {"value": "mimo-v2.5-pro", "label": "MiMo V2.5 Pro（高质量）"},
            {"value": "mimo-v2-pro", "label": "MiMo V2 Pro（文本推理）"},
            {"value": "mimo-v2-omni", "label": "MiMo V2 Omni（多模态推理）"},
            {"value": "mimo-v2-flash", "label": "MiMo V2 Flash（快速）"},
        ],
    },
    {
        "name": "Xiaomi MiMo（Token Plan 订阅）",
        "provider": "xiaomi-mimo-tp",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "chat_model": "mimo-v2.5",
        "work_model": "mimo-v2.5-pro",
        "embedding_model": "",
        "thinking_supported": True,
        "api_key_url": "https://platform.xiaomimimo.com/#/console/api-keys",
        "is_default": False,
        "model_options": [
            {"value": "mimo-v2.5", "label": "MiMo V2.5（多模态，推荐）"},
            {"value": "mimo-v2.5-pro", "label": "MiMo V2.5 Pro（高质量）"},
            {"value": "mimo-v2-pro", "label": "MiMo V2 Pro（文本推理）"},
            {"value": "mimo-v2-omni", "label": "MiMo V2 Omni（多模态推理）"},
            {"value": "mimo-v2-flash", "label": "MiMo V2 Flash（快速）"},
        ],
    },
]


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

    # 幂等：已有 xiaomi-mimo 则跳过
    existing_keys = {c.get("provider") for c in configs}
    if "xiaomi-mimo" in existing_keys:
        return

    configs.extend(MIMO_PRESETS)
    conn.execute(
        sa.text("UPDATE system_settings SET provider_config = CAST(:val AS jsonb) WHERE id = 1"),
        {"val": json.dumps(configs, ensure_ascii=False)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT provider_config FROM system_settings WHERE id = 1")
    )
    row = result.fetchone()
    if row is None or row[0] is None:
        return

    raw = row[0]
    configs = json.loads(raw) if isinstance(raw, str) else list(raw)
    configs = [c for c in configs if c.get("provider") not in ("xiaomi-mimo", "xiaomi-mimo-tp")]
    conn.execute(
        sa.text("UPDATE system_settings SET provider_config = CAST(:val AS jsonb) WHERE id = 1"),
        {"val": json.dumps(configs, ensure_ascii=False)},
    )
