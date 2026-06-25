# willind-mcp health 체크
$res = Invoke-WebRequest -Uri "http://127.0.0.1:3100/health" -UseBasicParsing
Write-Output $res.Content
