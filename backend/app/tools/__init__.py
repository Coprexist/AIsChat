"""
工具插件系统 — 自动发现并注册所有工具插件

每个工具是 ToolPlugin 子类，分布在子目录中。
导入此包会自动注册所有工具到 ToolRegistry。

添加新工具只需两步：
1. 在对应子目录创建 my_tool.py，定义 ToolPlugin 子类并在文件末调用 ToolRegistry.register()
2. 在此文件添加一行 import
"""

# ── chat_social ──
from app.tools.chat_social.send_message import SendMessage
from app.tools.chat_social.expand_message import ExpandMessage
from app.tools.chat_social.send_dm import SendDM
from app.tools.chat_social.set_dnd import SetDND
from app.tools.chat_social.mute_group import MuteGroup
from app.tools.chat_social.cancel_dnd import CancelDND
from app.tools.chat_social.enter_group import EnterGroup
from app.tools.chat_social.switch_state import SwitchState
from app.tools.chat_social.view_unread import ViewUnread
from app.tools.chat_social.list_available_skills import ListAvailableSkills
from app.tools.chat_social.cross_post import CrossPost
from app.tools.chat_social.send_file import SendFile
from app.tools.chat_social.send_friend_request import SendFriendRequest
from app.tools.chat_social.search_users import SearchUsers

# ── memory ──
from app.tools.memory.store_memory import StoreMemory
from app.tools.memory.recall_memory import RecallMemory
from app.tools.memory.manage_records import ManageRecords

# ── group_management ──
from app.tools.group_management.create_group import CreateGroup
from app.tools.group_management.invite_to_group import InviteToGroup

# ── self_config ──
from app.tools.self_config.update_self_config import UpdateSelfConfig
from app.tools.self_config.toggle_thinking import ToggleThinking
from app.tools.self_config.manage_skills import ManageSkills
from app.tools.self_config.set_status import SetStatus

# ── self_management ──
from app.tools.self_management.end_turn import EndTurn
from app.tools.self_management.push_state import PushState
from app.tools.self_management.pop_state import PopState
from app.tools.self_management.close_state import CloseState
from app.tools.self_management.list_states import ListStates
from app.tools.self_management.set_alarm import SetAlarm
from app.tools.self_management.cancel_alarm import CancelAlarm
from app.tools.self_management.update_alarm import UpdateAlarm
from app.tools.self_management.list_alarms import ListAlarms
from app.tools.self_management.check_workspace import CheckWorkspace
from app.tools.self_management.clear_current_task import ClearCurrentTask
from app.tools.self_management.manage_workspace import ManageWorkspace
from app.tools.self_management.compress_context import CompressContext
from app.tools.self_management.tool_help import ToolHelp

# ── file_operations ──
from app.tools.file_operations.execute_command import ExecuteCommand
from app.tools.file_operations.file_read import FileRead
from app.tools.file_operations.file_write import FileWrite
from app.tools.file_operations.file_list import FileList
from app.tools.file_operations.file_delete import FileDelete
from app.tools.file_operations.file_share import FileShare
