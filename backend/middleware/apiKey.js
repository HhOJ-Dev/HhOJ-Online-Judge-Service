const config = require('../config');

function timingSafeEqual(a, b) {
  if (a.length !== b.length) {
    return false;
  }
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

function requireApiKey(req, res, next) {
  const apiKey = req.headers['x-api-key'];
  const validApiKey = config.server.apiKey;
  
  if (!apiKey) {
    return res.status(401).json({
      success: false,
      message: 'Unauthorized: API key is required'
    });
  }

  if (!validApiKey) {
    return res.status(500).json({
      success: false,
      message: 'Server error: API key not configured'
    });
  }

  if (!timingSafeEqual(apiKey, validApiKey)) {
    return res.status(403).json({
      success: false,
      message: 'Forbidden: Invalid API key'
    });
  }

  next();
}

module.exports = requireApiKey;