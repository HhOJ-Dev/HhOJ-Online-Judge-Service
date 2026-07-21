const express = require('express');
const router = express.Router();
const githubService = require('../services/github');
const store = require('../services/store');

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

    // If not completed yet, return current status
    if (record.status !== 'completed') {
      return res.json({
        success: true,
        data: {
          judgeId,
          status: record.status,
          message: 'Judge is still in progress'
        }
      });
    }

    // Get result from GitHub artifact
    if (record.runId) {
      try {
        const result = await githubService.getResult(record.runId);
        
        res.json({
          success: true,
          data: {
            judgeId,
            status: 'completed',
            result: record.result,
            artifact: result,
            runId: record.runId
          }
        });
      } catch (error) {
        res.json({
          success: true,
          data: {
            judgeId,
            status: 'completed',
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
          status: 'completed',
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
router.post('/callback', async (req, res) => {
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
 * List all judge requests
 */
router.get('/list', (req, res) => {
  const list = store.list();
  res.json({
    success: true,
    data: list
  });
});

/**
 * GET /api/judge_fetch
 * Fetch pending submissions for GitHub Actions workflow
 * This is called by the judge workflow to get submissions to process
 */
router.get('/judge_fetch', (req, res) => {
  try {
    const apiKey = req.headers['x-api-key'];
    
    if (!apiKey || apiKey !== process.env.HHOJ_API_KEY) {
      return res.status(401).json({
        success: false,
        message: 'Unauthorized: Invalid API key'
      });
    }

    const batch = parseInt(req.query.batch) || 1;
    const pending = store.getPending(batch);

    const submissions = pending.map(item => ({
      id: item.judgeId,
      language: item.language,
      code: item.code,
      testcases: item.testcases,
      time_limit: item.config?.timeLimit || 2000,
      memory_limit: item.config?.memoryLimit || 256,
      submit_time: item.createdAt
    }));

    store.cleanup();

    res.json({
      success: true,
      submissions: submissions
    });

  } catch (error) {
    console.error('Judge fetch error:', error);
    res.status(500).json({
      success: false,
      message: 'Internal server error'
    });
  }
});

module.exports = router;