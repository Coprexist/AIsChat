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
