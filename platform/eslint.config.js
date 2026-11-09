import globals from 'globals'
import pluginJs from '@eslint/js'
import pluginTs from '@typescript-eslint/eslint-plugin'
import parserTs from '@typescript-eslint/parser'
import eslintPluginPrettierRecommended from 'eslint-plugin-prettier/recommended'

export default [
  {
    ignores: ['**/dist/**', 'node_modules/**', 'build/**', '.next/**', '.turbo/**', 'coverage/**'],
  },
  pluginJs.configs.recommended,
  eslintPluginPrettierRecommended,
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      globals: { ...globals.node },
      parser: parserTs,
      parserOptions: {
        tsconfigRootDir: import.meta.dirname,
        project: ['./tsconfig.json', './packages/*/tsconfig.json'],
      },
    },
    plugins: { '@typescript-eslint': pluginTs },
    rules: {
      ...pluginTs.configs.recommended.rules,
      'prettier/prettier': ['warn', { endOfLine: 'auto' }],
      'no-redeclare': 'off',
      '@typescript-eslint/no-redeclare': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/naming-convention': [
        'warn',
        { selector: 'variable', format: ['camelCase', 'PascalCase', 'UPPER_CASE'] },
        { selector: 'function', format: ['camelCase'] },
        { selector: 'method', format: ['camelCase'] },
        { selector: 'typeLike', format: ['PascalCase'] },
      ],
      // 'no-console': 'warn',
      'no-debugger': 'error',
    },
  },
]
