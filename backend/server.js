const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');

const judgeRoutes = require('./routes/judge');
const resultRoutes = require('./routes/result');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// Routes
app.use('/api', judgeRoutes);
app.use('/api', resultRoutes);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Error handling
app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(500).json({ success: false, error: err.message });
});

app.listen(PORT, () => {
  console.log(`HhOJ Backend Service running on port ${PORT}`);
});