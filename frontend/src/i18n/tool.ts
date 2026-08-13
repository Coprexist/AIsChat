/**
 * 工具翻译分区（i18n 命名空间思路，2026-08-13）
 *
 * 独立文件维护：AI 工具名/状态文案改动只改这里，不碰 5369 行主字典。
 * 未来其他分区（世界积木/商城等）同样模式加文件，translations.ts 运行时合并。
 *
 * key 结构：
 *   toolName.{name}    → 工具名（file_read → 读取文件）
 *   tool.{status}      → 状态模板（running/update/done，{name}/{summary} 插值）
 */

import type { TranslationDict } from './translations'

export const toolZh: TranslationDict = {
  'toolName.file_read': '读取文件',
  'toolName.file_edit': '编辑文件',
  'toolName.file_write': '写入文件',
  'toolName.file_grep': '搜索文件',
  'toolName.file_list': '列目录',
  'toolName.run_world_code': '运行代码',
  'toolName.web_search': '搜索网页',
  'toolName.web_fetch': '抓取网页',
  'toolName.web_download': '下载资源',
  'toolName.manage_records': '读写记忆',
  'toolName.update_world_info': '更新世界信息',
  'toolName.compact_context': '压缩上下文',
  'toolName.view_api_doc': '查看接口文档',
  'toolName.apply_world_block': '应用积木',
  'toolName.list_world_blocks': '浏览积木',
  'toolName.view_world_block': '查看积木',
  'toolName.suggest_questions': '生成建议',
  'toolName.send_group_message': '发群消息',
  'toolName.get_group_messages': '读群消息',
  'toolName.list_group_members': '列群成员',
  'toolName.get_group_types': '查群类型',
  'toolName.update_group_types': '配群类型',
  // 状态模板（{name}/{summary} 插值）
  'tool.running': '正在{name}…',
  'tool.update': '{summary}',
  'tool.done': '{summary}',
  'world.reasoning': '思考',
}

export const toolEn: TranslationDict = {
  'toolName.file_read': 'Read file',
  'toolName.file_edit': 'Edit file',
  'toolName.file_write': 'Write file',
  'toolName.file_grep': 'Search file',
  'toolName.file_list': 'List directory',
  'toolName.run_world_code': 'Run code',
  'toolName.web_search': 'Search web',
  'toolName.web_fetch': 'Fetch web',
  'toolName.web_download': 'Download asset',
  'toolName.manage_records': 'Manage memory',
  'toolName.update_world_info': 'Update world info',
  'toolName.compact_context': 'Compact context',
  'toolName.view_api_doc': 'View API docs',
  'toolName.apply_world_block': 'Apply block',
  'toolName.list_world_blocks': 'Browse blocks',
  'toolName.view_world_block': 'View block',
  'toolName.suggest_questions': 'Suggest questions',
  'toolName.send_group_message': 'Send group message',
  'toolName.get_group_messages': 'Read group messages',
  'toolName.list_group_members': 'List group members',
  'toolName.get_group_types': 'Get group types',
  'toolName.update_group_types': 'Configure group types',
  'tool.running': 'Running {name}…',
  'tool.update': '{summary}',
  'tool.done': '{summary}',
  'world.reasoning': 'Thinking',
}

export const toolJa: TranslationDict = {
  'toolName.file_read': 'ファイル読込',
  'toolName.file_edit': 'ファイル編集',
  'toolName.file_write': 'ファイル書込',
  'toolName.file_grep': 'ファイル検索',
  'toolName.file_list': 'ディレクトリ一覧',
  'toolName.run_world_code': 'コード実行',
  'toolName.web_search': 'Web検索',
  'toolName.web_fetch': 'Web取得',
  'toolName.web_download': 'リソース取得',
  'toolName.manage_records': '記憶管理',
  'toolName.update_world_info': '世界情報更新',
  'toolName.compact_context': 'コンテキスト圧縮',
  'toolName.view_api_doc': 'APIドキュメント表示',
  'toolName.apply_world_block': 'ブロック適用',
  'toolName.list_world_blocks': 'ブロック一覧',
  'toolName.view_world_block': 'ブロック表示',
  'toolName.suggest_questions': '提案生成',
  'toolName.send_group_message': 'グループメッセージ送信',
  'toolName.get_group_messages': 'グループメッセージ取得',
  'toolName.list_group_members': 'メンバー一覧',
  'toolName.get_group_types': 'グループタイプ取得',
  'toolName.update_group_types': 'グループタイプ設定',
  'tool.running': '{name}を実行中…',
  'tool.update': '{summary}',
  'tool.done': '{summary}',
  'world.reasoning': '思考',
}
