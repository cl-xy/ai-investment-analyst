# E2E CI Job Definition

Add this job to `.github/workflows/ci.yml` after the frontend build job passes.

```yaml
  test-e2e:
    runs-on: ubuntu-latest
    needs: [build-frontend]
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: |
            package-lock.json
            frontend/package-lock.json

      - name: Install root dependencies
        run: npm ci

      - name: Install frontend dependencies
        working-directory: frontend
        run: npm ci

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium firefox

      - name: Run E2E tests
        run: npm run test:e2e
        env:
          CI: true

      - name: Upload test results
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 7

      - name: Upload traces on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-traces
          path: test-results/
          retention-days: 7
```

## Notes

- The `needs: [build-frontend]` ensures the frontend builds cleanly before running E2E.
- Playwright's `webServer` config in `playwright.config.ts` automatically starts the Vite dev server.
- Traces are only uploaded on failure to save artifact storage.
- The `github` reporter is automatically used when `CI=true` (configured in playwright.config.ts).
- Timeout is set to 10 minutes. SSE streaming tests may take longer than unit tests.
