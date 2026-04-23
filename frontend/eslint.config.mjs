// ESLint flat config — trimmed companion to biome.json.
// Biome handles fast syntactic rules and (optionally) formatting.
// ESLint keeps ONLY the rules Biome can't do: type-aware checks and
// plugin-specific checks (import resolution, sonarjs complexity, security).
//
// Rationale and tier-by-tier breakdown: see https://github.com/sneg55/agent-starter
// guides/lint-rules-for-ai.md.
//
// Assumes: ESLint >= 9, TypeScript, type-aware linting via projectService.

import tseslint from 'typescript-eslint'
import importPlugin from 'eslint-plugin-import'
import sonarjs from 'eslint-plugin-sonarjs'
import security from 'eslint-plugin-security'
import comments from 'eslint-plugin-eslint-comments'

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'build/**',
      'coverage/**',
      'node_modules/**',
      '.next/**',
      '*.config.*',
      'src/lib/api-types.d.ts',
    ],
  },

  ...tseslint.configs.recommendedTypeChecked,

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: {
      import: importPlugin,
      sonarjs,
      security,
      'eslint-comments': comments,
    },
    rules: {
      // ── Tier 1: Type-aware correctness (Biome cannot do these) ─────────────
      // Async bugs — the highest-value AI guardrails.
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
      '@typescript-eslint/require-await': 'error',
      '@typescript-eslint/await-thenable': 'error',
      '@typescript-eslint/return-await': ['error', 'always'],

      // Type-unsafe escape hatches.
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-call': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-unsafe-return': 'error',
      '@typescript-eslint/no-unsafe-argument': 'error',
      '@typescript-eslint/switch-exhaustiveness-check': 'error',
      '@typescript-eslint/only-throw-error': 'error',
      '@typescript-eslint/prefer-readonly': 'error',

      // Disabled: fights React/Next.js idioms like `{user && <X/>}` on nullable strings.
      '@typescript-eslint/strict-boolean-expressions': 'off',
      // Disabled: flags defensive optional chaining on API-response unions as "unnecessary".
      '@typescript-eslint/no-unnecessary-condition': 'off',
      // Disabled: autofix strips assertions (e.g. `as HTMLInputElement`) that tsc needs.
      '@typescript-eslint/no-unnecessary-type-assertion': 'off',
      // Disabled: `||` with empty-string/0 fallbacks is idiomatic; `??` has different semantics.
      '@typescript-eslint/prefer-nullish-coalescing': 'off',

      // ── Turn OFF rules Biome owns, so they don't double-fire ───────────────
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/consistent-type-imports': 'off',
      '@typescript-eslint/consistent-type-definitions': 'off',
      '@typescript-eslint/array-type': 'off',
      '@typescript-eslint/prefer-optional-chain': 'off',
      'no-var': 'off',
      'prefer-const': 'off',
      'no-empty': 'off',
      'no-empty-function': 'off',
      'no-unreachable': 'off',
      'no-constant-condition': 'off',
      'no-self-compare': 'off',
      'no-unused-private-class-members': 'off',
      'no-console': 'off',
      'no-debugger': 'off',
      'prefer-template': 'off',
      'object-shorthand': 'off',

      // ── Kept beyond Biome: semantic checks Biome doesn't cover ─────────────
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'no-throw-literal': 'error',
      'no-alert': 'error',
      'no-warning-comments': [
        'warn',
        { terms: ['fixme', 'xxx', 'hack'], location: 'anywhere' },
      ],
      'no-restricted-properties': [
        'error',
        {
          object: 'process',
          property: 'env',
          message: 'Inject config at the boundary; do not read process.env deep in modules.',
        },
      ],
      'no-constant-binary-expression': 'error',

      // ── Tier 2: Imports (catches hallucinated modules — Biome can't resolve) ─
      // Disabled: no TS resolver wired up; tsc --noEmit already catches unresolved imports.
      'import/no-unresolved': 'off',
      'import/no-cycle': ['error', { maxDepth: 10 }],
      'import/no-self-import': 'error',
      'import/no-duplicates': 'error',
      'import/no-extraneous-dependencies': 'error',
      'import/first': 'error',
      'import/newline-after-import': 'error',
      // Deep relative paths; package-name restrictions live in biome.json.
      'no-restricted-imports': ['error', { patterns: ['../../../*'] }],

      // ── Tier 3: Agent-specific traps (plugin-only) ─────────────────────────
      'eslint-comments/require-description': ['error', { ignore: [] }],
      'eslint-comments/no-unlimited-disable': 'error',
      'eslint-comments/no-unused-disable': 'error',

      // ── Tier 4: Complexity (sonarjs — Biome has noExcessiveCognitiveComplexity
      //    but sonarjs's heuristics are more mature) ─────────────────────────
      'sonarjs/cognitive-complexity': ['error', 15],
      'sonarjs/no-duplicate-string': ['error', { threshold: 5 }],
      'sonarjs/no-identical-functions': 'error',
      'sonarjs/no-collapsible-if': 'error',
      'sonarjs/prefer-immediate-return': 'error',
      // Disabled: overlaps with sonarjs/cognitive-complexity. See GH #79.
      complexity: 'off',
      'max-depth': ['warn', 4],
      'max-nested-callbacks': ['warn', 3],
      'max-params': ['warn', 4],

      // ── Tier 5: Security (Biome only has noGlobalEval) ─────────────────────
      // Disabled: false positives on typed record/enum lookups; tsc covers real risk.
      'security/detect-object-injection': 'off',
      'security/detect-non-literal-regexp': 'warn',
      'security/detect-unsafe-regex': 'error',
      'security/detect-eval-with-expression': 'error',
      'security/detect-child-process': 'warn',
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
    },
  },

  // Tests: loosen the rules that fight legitimate test patterns.
  {
    files: ['**/*.{test,spec}.{ts,tsx}', 'tests/**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-misused-promises': 'off',
      '@typescript-eslint/no-floating-promises': 'off',
      '@typescript-eslint/require-await': 'off',
      'sonarjs/no-duplicate-string': 'off',
      'max-nested-callbacks': 'off',
      'no-restricted-properties': 'off',
    },
  },
)
