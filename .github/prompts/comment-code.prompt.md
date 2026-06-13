---
name: comment-code
description: Add useful commentary to selected code or changed files.
agent: Docs Maintainer
---

Review the selected code or the changed files in this repository.

Add useful code comments only where they help explain:
- business logic
- data transformation
- Power BI custom visual behaviour
- capabilities/data role handling
- formatting pane logic
- edge cases
- non-obvious TypeScript
- performance-sensitive logic

Do not add obvious comments like "increment counter" or "set variable".

Prefer:
- TSDoc for exported functions/classes/interfaces
- short inline comments for tricky implementation details
- section comments only where they improve readability

After editing, provide:
1. Files changed
2. Comments added
3. Anything that should be documented in README.md