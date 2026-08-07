const { Octokit } = require('@octokit/rest');
const config = require('../config');
const fs = require('fs');
const path = require('path');
const AdmZip = require('adm-zip');

class GitHubService {
  constructor() {
    this.octokit = new Octokit({
      auth: config.github.token
    });
  }

  async triggerWorkflow(payload) {
    const { owner, repo, workflowId, ref } = config.github;

    try {
      await this.octokit.actions.createWorkflowDispatch({
        owner,
        repo,
        workflow_id: workflowId,
        ref: ref || 'main',
        inputs: {
          judge_id: payload.judgeId,
          language: payload.language,
          code: payload.code,
          testcases: JSON.stringify(payload.testcases),
          config: JSON.stringify(payload.config || {})
        }
      });

      const runs = await this.octokit.actions.listWorkflowRuns({
        owner,
        repo,
        workflow_id: workflowId,
        per_page: 1
      });

      if (runs.data.workflow_runs.length > 0) {
        return runs.data.workflow_runs[0].id;
      }

      return null;
    } catch (error) {
      console.error('Failed to trigger workflow:', error);
      throw error;
    }
  }

  async getRunStatus(runId) {
    const { owner, repo } = config.github;

    try {
      const response = await this.octokit.actions.getWorkflowRun({
        owner,
        repo,
        run_id: runId
      });

      const run = response.data;

      return {
        id: run.id,
        status: run.status,
        conclusion: run.conclusion,
        html_url: run.html_url,
        created_at: run.created_at,
        updated_at: run.updated_at
      };
    } catch (error) {
      console.error('Failed to get run status:', error);
      throw error;
    }
  }

  async getResult(runId) {
    const { owner, repo } = config.github;

    try {
      const artifacts = await this.octokit.actions.listWorkflowRunArtifacts({
        owner,
        repo,
        run_id: runId
      });

      const resultArtifact = artifacts.data.artifacts.find(
        a => a.name === 'judge-results'
      );

      if (!resultArtifact) {
        return null;
      }

      const download = await this.octokit.actions.downloadArtifact({
        owner,
        repo,
        artifact_id: resultArtifact.id,
        archive_format: 'zip'
      });

      const tempDir = path.join(__dirname, '../temp');
      if (!fs.existsSync(tempDir)) {
        fs.mkdirSync(tempDir, { recursive: true });
      }

      const zipPath = path.join(tempDir, `artifact_${runId}.zip`);
      const zipBuffer = Buffer.isBuffer(download.data) ? download.data : Buffer.from(download.data);
      fs.writeFileSync(zipPath, zipBuffer);

      let resultData = null;
      try {
        const zip = new AdmZip(zipPath);
        const entries = zip.getEntries();

        for (const entry of entries) {
          if (entry.entryName === 'judge_result.json') {
            const content = zip.readAsText(entry);
            resultData = JSON.parse(content);
            break;
          }
        }
      } catch (parseError) {
        console.error('Failed to parse artifact:', parseError);
      }

      try {
        fs.unlinkSync(zipPath);
      } catch {
        // Ignore cleanup errors
      }

      return {
        artifactId: resultArtifact.id,
        downloadUrl: download.url,
        result: resultData
      };
    } catch (error) {
      console.error('Failed to get result:', error);
      throw error;
    }
  }

  async getLogs(runId) {
    const { owner, repo } = config.github;

    try {
      const response = await this.octokit.actions.downloadWorkflowRunLogs({
        owner,
        repo,
        run_id: runId
      });

      return response.url;
    } catch (error) {
      console.error('Failed to get logs:', error);
      throw error;
    }
  }
}

module.exports = new GitHubService();
