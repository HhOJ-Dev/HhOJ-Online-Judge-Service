const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const http = require('http');
const { WebSocketServer } = require('ws');
const url = require('url');
const rateLimit = require('express-rate-limit');
const { spawn } = require('child_process');
const path = require('path');

const judgeRoutes = require('./routes/judge');
const resultRoutes = require('./routes/result');
const githubActionsRoutes = require('./routes/githubActions');
const wsManager = require('./services/wsManager');
const hhojRoutes = require('./routes/hhoj.js');
const config = require('./config');
const store = require('./services/store');

const app = express();
const PORT = process.env.PORT || 3000;

const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 30,
  standardHeaders: true,
  legacyHeaders: false,
  message: { success: false, error: 'Too many requests, please try again later' }
});

const judgeLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: config.judge.mode === 'direct' ? 60 : 5, // direct模式放宽限制（评测只需~500ms）
  standardHeaders: true,
  legacyHeaders: false,
  message: { success: false, error: 'Judge requests rate limited, please wait' }
});

const allowedOrigins = process.env.CORS_ORIGINS
  ? process.env.CORS_ORIGINS.split(',')
  : ['*'];

app.use(cors({
  origin: allowedOrigins,
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'X-API-Key']
}));

app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// Apply rate limiters selectively:
// - judgeLimiter: only on POST /api/judge (submission)
// - apiLimiter: only on mutation endpoints, NOT on status/result polling
app.use('/api/judge', judgeLimiter);
app.use('/api', (req, res, next) => {
  // Skip rate limiting for polling and internal worker endpoints
  const path = req.path;
  if (path === '/judge_fetch.php' || 
      path === '/judge_report.php' ||
      path.startsWith('/status/') ||
      path.startsWith('/result/')) {
    return next();
  }
  apiLimiter(req, res, next);
});

app.use('/api', judgeRoutes);
app.use('/api', resultRoutes);
app.use('/api', githubActionsRoutes);
app.use('/api', hhojRoutes);

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(500).json({ success: false, error: err.message });
});

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

wss.on('connection', (ws, req) => {
  const parsedUrl = url.parse(req.url, true);
  const judgeId = parsedUrl.query.judgeId;

  if (!judgeId) {
    ws.send(JSON.stringify({ type: 'error', message: 'Missing judgeId parameter' }));
    ws.close(4001, 'Missing judgeId');
    return;
  }

  wsManager.subscribe(judgeId, ws);
  ws.send(JSON.stringify({ type: 'connected', judgeId }));
});

setInterval(() => {
  store.cleanup(3600000);
}, 600000);

server.listen(PORT, () => {
  console.log(`HhOJ Backend Service running on port ${PORT}`);
  console.log(`WebSocket server listening on ws://localhost:${PORT}/ws`);
  console.log('Memory store auto-cleanup enabled (every 10 minutes)');
  console.log(`Judge mode: ${config.judge.mode || 'direct'}`);

  // Auto-spawn direct judge worker if in direct or hybrid mode
  if (config.judge.mode === 'direct' || config.judge.mode === 'hybrid') {
    const workerScript = path.join(__dirname, '..', 'blankend', 'judge_worker.py');
    const apiKey = config.server.apiKey || '';

    console.log(`Starting judge worker: ${workerScript}`);

    const worker = spawn('python3', [
      workerScript,
      '--host', `http://localhost:${PORT}`,
      '--api-key', apiKey,
      '--poll-interval', '100'
    ], {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, HHOJ_API_KEY: apiKey }
    });

    worker.stdout.on('data', (data) => {
      process.stdout.write(`[judge-worker] ${data}`);
    });

    worker.stderr.on('data', (data) => {
      process.stderr.write(`[judge-worker] ${data}`);
    });

    worker.on('error', (err) => {
      console.error('Judge worker failed to start:', err.message);
    });

    worker.on('close', (code) => {
      console.log(`Judge worker exited with code ${code}`);
    });

    // Clean shutdown
    const shutdown = () => {
      worker.kill('SIGTERM');
      process.exit();
    };
    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
  }
});
