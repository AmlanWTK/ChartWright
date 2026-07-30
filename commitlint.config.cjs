// Conventional Commits enforcement.
// Format: <type>(<optional scope>): <subject>
// Example: feat(ingestion): add malware scan on upload
module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      ["feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"],
    ],
    "scope-case": [2, "always", "kebab-case"],
    "subject-case": [2, "never", ["upper-case", "pascal-case"]],
    "header-max-length": [2, "always", 100],
  },
};
