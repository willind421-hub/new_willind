import './env.js'
import { initDb } from './db/database.js'
import { createMcpApp } from './mcp/server.js'

async function main() {
  initDb()
  console.log('DB 초기화 완료')

  const port = Number(process.env.MCP_PORT ?? 3100)
  const httpServer = createMcpApp().listen(port, '127.0.0.1', () => {
    console.log(`MCP 서버 시작: http://127.0.0.1:${port}`)
  })

  async function shutdown(signal: string) {
    console.log(`${signal} 수신 — graceful shutdown 시작`)
    await Promise.race([
      new Promise<void>((resolve) => httpServer.close(() => resolve())),
      new Promise<void>((resolve) => setTimeout(resolve, 5000)),
    ])
    console.log('graceful shutdown 완료')
    process.exit(0)
  }
  process.on('SIGTERM', () => { void shutdown('SIGTERM') })
  process.on('SIGINT', () => { void shutdown('SIGINT') })
}

main().catch((err) => { console.error('서버 시작 실패:', err); process.exit(1) })
