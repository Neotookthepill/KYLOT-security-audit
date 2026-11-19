const globals = require("globals");

/** Configuration minimale : attrape les variables utilisées sans import. */
module.exports = [
  { ignores: ["build/**", "node_modules/**", "e2e/**"] },
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node, ...globals.jest },
    },
    plugins: { "react-hooks": require("eslint-plugin-react-hooks") },
    rules: {
      "no-undef": "error",
    },
  },
];
