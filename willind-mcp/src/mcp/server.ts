import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js'
import express from 'express'

// 빈 MCP 서버 뼈대 — 도구(tool)는 사용자가 여기에 추가한다.
//
// 예시:
//   import { z } from 'zod'
//   server.tool(
//     'my_tool',
//     '도구 설명',
//     { arg: z.string() },
//     async ({ arg }) => ({ content: [{ type: 'text' as const, text: `결과: ${arg}` }] }),
//   )
function buildMcpServer() {
  const server = new McpServer({ name: 'willind-mcp', version: '1.0.0' })
  // TODO: 자신의 MCP 도구를 여기에 등록하세요.
  return server
}

export function createMcpApp(): express.Application {
  const app = express()
  app.use(express.json())

  app.get('/health', (_req, res) => {
    res.json({ ok: true, service: 'willind-mcp', version: '1.0.0', mcp: '/mcp' })
  })

  // API 키 인증 — .env의 API_KEY와 x-api-key 헤더가 일치해야 통과
  app.use((req, res, next) => {
    const apiKey = process.env.API_KEY
    if (!apiKey || req.headers['x-api-key'] !== apiKey) {
      res.status(401).json({ error: 'Unauthorized' })
      return
    }
    next()
  })

  app.post('/mcp', async (req, res) => {
    const server = buildMcpServer()
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined })
    await server.connect(transport)
    await transport.handleRequest(req, res, req.body)
  })

  return app
}
