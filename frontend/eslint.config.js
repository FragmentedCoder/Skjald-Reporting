import svelte from "eslint-plugin-svelte";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";

export default [
  {
    files: ["**/*.ts", "**/*.svelte"],
    languageOptions: {
      parser: tsParser,
    },
    plugins: { "@typescript-eslint": tseslint },
    rules: {},
  },
  ...svelte.configs.recommended,
  {
    ignores: [".svelte-kit/", "build/", "node_modules/"],
  },
];
