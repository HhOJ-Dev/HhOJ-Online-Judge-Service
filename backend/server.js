const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const http = require('http');
const { WebSocketServer } = require('ws');
const url = require('url');
const rateLimit = require('express-rate-limit');

const judgeRoutes = require('./routes/judge');
const resultRoutes = require('./routes/result');
const githubActionsRoutes = require('./routes/githubActions');
const wsManager = require('./services/wsManager');
const hhojRoutes = require('./routes/hhoj.js');
const wsManager = require('./services/wsManager');
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
  max: 5,
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

app.use('/api', apiLimiter);
app.use('/api/judge', judgeLimiter);

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

// Create HTTP server and WebSocket server
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

server.listen(PORT, () => {
  console.log(`HhOJ Backend Service running on port ${PORT}`);
  console.log(`WebSocket server listening on ws://localhost:${PORT}/ws`);
setInterval(() => {
  store.cleanup(3600000);
}, 600000);

server.listen(PORT, () => {
  console.log(`HhOJ Backend Service running on port ${PORT}`);
  console.log(`WebSocket server listening on ws://localhost:${PORT}/ws`);
  console.log('Memory store auto-cleanup enabled (every 10 minutes)');
});
