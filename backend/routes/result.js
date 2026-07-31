const express = require('express');
const router = express.Router();
const githubService = require('../services/github');
const store = require('../services/store');
const requireApiKey = require('../middleware/apiKey');

/**
 * GET /api/result/:judgeId
 * Get judge result
 */
router.get('/result/:judgeId', async (req, res) => {
  try {
    const { judgeId } = req.params;
    const record = store.get(judgeId);

    if (!record) {
      return res.status(404).json({
        success: false,
        error: 'Judge request not found'
      });
    }

    // If completed or error, return the result
    if (record.status !== 'completed' && record.status !== 'error') {
      return res.json({
        success: true,
        data: {
          judgeId,
          status: record.status,
          message: 'Judge is still in progress'
        }
      });
    }

    // If result already stored (e.g. from callback), return immediately
    // to avoid slow GitHub artifact download (~30s)
    if (record.result) {
      return res.json({
        success: true,
        data: {
          judgeId,
          status: record.status,
          result: record.result
        }
      });
    }

    // Get result from GitHub artifact (only if not already in store)
    if (record.runId) {
      try {
        const result = await githubService.getResult(record.runId);
        
        res.json({
          success: true,
          data: {
            judgeId,
            status: record.status,
            result: record.result || result?.result,
            artifact: result,
            runId: record.runId
          }
        });
      } catch (error) {
        res.json({
          success: true,
          data: {
            judgeId,
            status: record.status,
            result: record.result,
            runId: record.runId,
            artifactError: error.message
          }
        });
      }
    } else {
      res.json({
        success: true,
        data: {
          judgeId,
          status: record.status,
          result: record.result
        }
      });
    }

  } catch (error) {
    console.error('Result error:', error);
    res.status(500).json({
      success: false,
      error: 'Internal server error'
    });
  }
});

/**
 * POST /api/callback
 * Receive judge result callback from GitHub Actions
 * This endpoint is called by the workflow when it completes
 */
router.post('/callback', requireApiKey, async (req, res) => {
  try {
    const { judgeId, result } = req.body;

    if (!judgeId) {
      return res.status(400).json({
        success: false,
        error: 'Missing judgeId'
      });
    }

    const record = store.get(judgeId);
    if (!record) {
      return res.status(404).json({
        success: false,
        error: 'Judge request not found'
      });
    }

    // Update store with result
    store.update(judgeId, {
      status: 'completed',
      result: result
    });

    res.json({
      success: true,
      message: 'Result received'
    });

  } catch (error) {
    console.error('Callback error:', error);
    res.status(500).json({
      success: false,
      error: 'Internal server error'
    });
  }
});

/**
 * GET /api/list
 * List all judge requests (requires API Key)
 */
router.get('/list', requireApiKey, (req, res) => {
  const list = store.list();
  res.json({
    success: true,
    data: list
  });
});

module.exports = router;