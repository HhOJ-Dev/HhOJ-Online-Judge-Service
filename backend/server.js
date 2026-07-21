const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const http = require('http');
const { WebSocketServer } = require('ws');
const url = require('url');

const judgeRoutes = require('./routes/judge');
const resultRoutes = require('./routes/result');
const githubActionsRoutes = require('./routes/githubActions');
const wsManager = require('./services/wsManager');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// Routes
app.use('/api', judgeRoutes);
app.use('/api', resultRoutes);
app.use('/api', githubActionsRoutes);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Error handling
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
});
