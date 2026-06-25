module.exports = {
  apps: [{
    name: 'willind-mcp',
    script: 'node_modules/tsx/dist/cli.mjs',
    args: 'src/index.ts',
    interpreter: 'node',
    cwd: '.',
    watch: false,
    // The command-center launcher is the primary owner for willind-mcp.
    // Keep this PM2 entry as a manual compatibility launcher only; otherwise a
    // port conflict on 3100/3101 turns into a restart loop.
    autorestart: false,
    windowsHide: true,
    restart_delay: 5000,
    env: {
      TELEGRAM_MCP_POLLING_ENABLED: 'false',
    },
  }],
}
