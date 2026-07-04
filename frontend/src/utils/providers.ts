/** 读取聊天样式（纯函数，读 localStorage，带默认值） */
export function getChatStyle(): 'cozy' | 'compact' {
  try { return (localStorage.getItem('chat_style') as 'cozy' | 'compact') || 'cozy' } catch { return 'cozy' }
}

/** 根据聊天样式返回间距/尺寸类名 */
export function chatStyleClasses(style: 'cozy' | 'compact') {
  if (style === 'compact') return { gap: 'gap-2', mb: 'mb-3', avatar: 'w-7 h-7', textSize: 'text-[10px]' }
  return { gap: 'gap-3', mb: 'mb-5', avatar: 'w-9 h-9', textSize: 'text-xs' }
}

/** 供应商纯数据工具（零 IO、零状态） */

/** 根据 API base_url 返回获取 Key 的官网链接（纯函数） */
export function getApiKeyUrl(baseUrl: string): string {
  const url = baseUrl.toLowerCase()
  if (url.includes('deepseek.com')) return 'https://platform.deepseek.com/api_keys'
  if (url.includes('openai.com')) return 'https://platform.openai.com/api-keys'
  if (url.includes('dashscope') || url.includes('aliyuncs.com')) return 'https://dashscope.console.aliyun.com/apiKey'
  if (url.includes('moonshot.cn')) return 'https://platform.moonshot.cn/console/api-keys'
  if (url.includes('bigmodel.cn')) return 'https://open.bigmodel.cn/usercenter/apikeys'
  if (url.includes('siliconflow.cn')) return 'https://cloud.siliconflow.cn/account/ak'
  return ''
}
