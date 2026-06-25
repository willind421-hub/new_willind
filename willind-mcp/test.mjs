// willind-mcp health 체크 — 서버 기동 후 인증·health 응답 확인
const res = await fetch('http://127.0.0.1:3100/health')
console.log(res.status, await res.text())
