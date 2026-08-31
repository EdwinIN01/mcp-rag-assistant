import { useAuthStore } from '../stores/auth'

/**
 * fetch 版 SSE 消费器（EventSource 不支持 POST + 自定义头，必须用 fetch 流式读取）。
 *
 * 后端事件序列（chat/stream）：
 *   event: sources → { sources: [...], latency_ms }
 *   event: delta    → { content: '...' }（多次）
 *   event: done     → {}
 */
export async function streamChat(message, history, callbacks) {
  const auth = useAuthStore()
  const resp = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.token}`,
    },
    body: JSON.stringify({ message, history }),
  })

  if (!resp.ok || !resp.body) {
    throw new Error(`流式请求失败（${resp.status}）`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  // 手动解析 SSE 帧：以空行分隔，event:/data: 两行组成
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() // 末帧可能不完整，留到下一轮

    for (const frame of frames) {
      let event = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!data) continue
      try {
        const payload = JSON.parse(data)
        if (event === 'sources') callbacks.onSources?.(payload)
        else if (event === 'delta') callbacks.onDelta?.(payload.content || '')
        else if (event === 'done') callbacks.onDone?.(payload)
      } catch {
        // 非 JSON 数据帧忽略
      }
    }
  }
  callbacks.onDone?.({})
}
