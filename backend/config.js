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
    defaultTimeLimit: 1000,   // ms
    defaultMemoryLimit: 256,  // MB
    supportedLanguages: [
      'c',
      'cpp',
      'cpp11', 'cpp11_o2',
      'cpp14', 'cpp14_o2',
      'cpp17', 'cpp17_o2',
      'cpp23', 'cpp23_o2',
      'python', 'python3',
      'java',
      'csharp',
      'pascal'
    ]
  }
};
