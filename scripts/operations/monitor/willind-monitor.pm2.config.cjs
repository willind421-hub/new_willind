/**
 * willind-monitor PM2 scheduled entry.
 *
 * Registration only:
 *   pm2 start C:/new_willind/scripts/operations/monitor/willind-monitor.pm2.config.cjs
 *   pm2 save
 *
 * This config is intentionally not started by smoke. The runner performs
 * read-only probes and does not start, stop, or delete services.
 */
const path = require('path');

const root = process.env.WILLIND_ROOT || process.cwd();
const python = process.env.WILLIND_PYTHON || 'python';
const runner = path.join(root, 'scripts', 'operations', 'monitor', 'willind_monitor_runner.py');
const logDir = path.join(root, 'runtime', 'monitor', 'willind-monitor', 'logs');

module.exports = {
  apps: [
    {
      name: 'willind-monitor',
      script: runner,
      args: '--mode once --json --write-output',
      interpreter: python,
      cwd: root,
      cron_restart: '*/5 * * * *',
      autorestart: false,
      watch: false,
      windowsHide: true,
      out_file: path.join(logDir, 'willind-monitor.out.log'),
      error_file: path.join(logDir, 'willind-monitor.err.log'),
      merge_logs: true,
      time: true,
      env: {
        WILLIND_MONITOR_MODE: 'pm2-cron',
      },
    },
  ],
};

