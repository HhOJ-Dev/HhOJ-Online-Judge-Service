// GitHub configuration
// Copy this file to config.local.js and fill in your values

module.exports = {
  // GitHub repository configuration
  github: {
    owner: process.env.GITHUB_OWNER || 'your-github-username',
    repo: process.env.GITHUB_REPO || 'HhOJ-Online-Judge-Service',
    token: process.env.GITHUB_TOKEN || '', // Personal Access Token with repo scope
    workflowId: 'judge.yml', // The workflow file name
    ref: process.env.GITHUB_REF || 'main' // Branch/tag ref to dispatch on
  },

  // Server configuration
  server: {
    port: process.env.PORT || 3000
  },

  // Judge configuration
  judge: {
    defaultTimeLimit: 2000,   // ms
    defaultMemoryLimit: 256,  // MB
    supportedLanguages: ['cpp', 'c', 'python', 'java', 'go', 'rust', 'javascript', 'csharp']
  }
};
