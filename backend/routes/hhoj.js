const express = require('express');
const router = express.Router();
const store = require('../services/store');
const requireApiKey = require('../middleware/apiKey');

router.get('/judge_fetch.php', requireApiKey, (req, res) => {
  const batch = parseInt(req.query.batch) || 1;
  const inlineTestcases = parseInt(req.query.inline_testcases) || 1;

  const pending = store.listPending(batch);

  const submissions = pending.map(item => {
    const submission = {
      id: item.judgeId,
      language: item.language,
      code: item.code,
      time_limit: item.config?.timeLimit || 1000,
      memory_limit: item.config?.memoryLimit || 256
    };

    if (inlineTestcases && item.testcases) {
      submission.testcases = item.testcases.map((tc, idx) => {
        let inputData = '';
        let outputData = '';

        if (tc.input) {
          inputData = Buffer.from(tc.input, 'utf-8').toString('base64');
        } else if (tc.input_data) {
          inputData = tc.input_data;
        }

        if (tc.output) {
          outputData = Buffer.from(tc.output, 'utf-8').toString('base64');
        } else if (tc.output_data) {
          outputData = tc.output_data;
        }

        return {
          id: idx,
          inlined: true,
          input_data: inputData,
          output_data: outputData,
          score: tc.score || 10
        };
      });
    } else if (item.testcases) {
      submission.testcases = item.testcases.map((tc, idx) => ({
        id: idx,
        input_url: tc.inputUrl || tc.input_url || '',
        output_url: tc.outputUrl || tc.output_url || '',
        score: tc.score || 10
      }));
    }

    store.update(item.judgeId, { status: 'fetching' });

    return submission;
  });

  res.json({
    success: true,
    submissions: submissions,
    message: `${submissions.length} submission(s) fetched`
  });
});

router.post('/judge_report.php', requireApiKey, (req, res) => {
  const { results } = req.body;

  if (!results || !Array.isArray(results)) {
    return res.json({
      success: false,
      message: 'Invalid results format'
    });
  }

  let successCount = 0;
  for (const result of results) {
    const submissionId = result.submission_id;
    const record = store.get(submissionId);

    if (record) {
      const hhojResult = {
        status: result.status,
        score: result.score,
        time_used: result.time_used,
        memory_used: result.memory_used,
        error_message: result.error_message || ''
      };

      let finalStatus = 'completed';
      if (result.status === 'ce') finalStatus = 'error';
      else if (result.status === 're') finalStatus = 'error';

      store.update(submissionId, {
        status: finalStatus,
        result: hhojResult,
        conclusion: result.status === 'accepted' ? 'success' : 'failure'
      });
      successCount++;
    }
  }

  res.json({
    success: true,
    message: `${successCount}/${results.length} results reported successfully`
  });
});

module.exports = router;
