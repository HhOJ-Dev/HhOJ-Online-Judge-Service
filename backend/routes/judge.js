const express = require('express');
const router = express.Router();
const { v4: uuidv4 } = require('uuid');
const githubService = require('../services/github');
const store = require('../services/store');
const config = require('../config');
const requireApiKey = require('../middleware/apiKey');

/**
 * POST /api/judge
 * Submit code for judging
 */
router.post('/judge', async (req, res) => {
  try {
    const { language, code, testcases, config: judgeConfig } = req.body;

    // Validation
    if (!language || !code || !testcases || !Array.isArray(testcases)) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields: language, code, testcases'
      });
    }

    if (!config.judge.supportedLanguages.includes(language)) {
      return res.status(400).json({
        success: false,
        error: `Unsupported language: ${language}. Supported: ${config.judge.supportedLanguages.join(', ')}`
      });
    }

    if (testcases.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'At least one testcase is required'
      });
    }

    // Generate judge ID
    const judgeId = uuidv4();

    // Prepare payload
    const payload = {
      judgeId,
      language,
      code,
      testcases,
      config: {
        timeLimit: judgeConfig?.timeLimit || config.judge.defaultTimeLimit,
        memoryLimit: judgeConfig?.memoryLimit || config.judge.defaultMemoryLimit
      }
    };

    // Save to store with complete data for GitHub Actions
    store.save(judgeId, {
      status: 'pending',
      language,
      code,
      testcases,
      config: {
        timeLimit: judgeConfig?.timeLimit || config.judge.defaultTimeLimit,
        memoryLimit: judgeConfig?.memoryLimit || config.judge.defaultMemoryLimit
      },
      testcasesCount: testcases.length
    });

    // Trigger GitHub Actions workflow
    let runId = null;
    try {
      runId = await githubService.triggerWorkflow(payload);
      store.update(judgeId, {
        runId,
        status: 'queued'
      });
    } catch (error) {
      store.update(judgeId, {
        status: 'error',
        error: error.message
      });
      return res.status(500).json({
        success: false,
        error: 'Failed to trigger judge workflow',
        details: error.message
      });
    }

    res.json({
      success: true,
      data: {
        judgeId,
        runId,
        status: 'queued',
        message: 'Judge request submitted successfully'
      }
    });

  } catch (error) {
    console.error('Judge error:', error);
    res.status(500).json({
      success: false,
      error: 'Internal server error',
      details: error.message
    });
  }
});

/**
 * GET /api/status/:judgeId
 * Get judge status (requires API Key)
 */
router.get('/status/:judgeId', requireApiKey, async (req, res) => {
  try {
    const { judgeId } = req.params;
    const record = store.get(judgeId);

    if (!record) {
      return res.status(404).json({
        success: false,
        error: 'Judge request not found'
      });
    }

    // If we have a runId, check GitHub for latest status
    if (record.runId && record.status !== 'completed' && record.status !== 'error') {
      try {
        const runStatus = await githubService.getRunStatus(record.runId);
        store.update(judgeId, {
          status: runStatus.status,
          conclusion: runStatus.conclusion
        });
        record.status = runStatus.status;
        record.conclusion = runStatus.conclusion;
      } catch (error) {
        console.error('Failed to check run status:', error);
      }
    }

    res.json({
      success: true,
      data: {
        judgeId,
        status: record.status,
        conclusion: record.conclusion,
        createdAt: record.createdAt,
        updatedAt: record.updatedAt
      }
    });

  } catch (error) {
    console.error('Status check error:', error);
    res.status(500).json({
      success: false,
      error: 'Internal server error'
    });
  }
});

module.exports = router;