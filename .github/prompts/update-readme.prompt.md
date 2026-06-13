---
name: update-readme
description: Update README.md based on the current project state and recent code changes.
agent: Docs Maintainer
---

Update README.md so it matches the current repository.

Inspect relevant files before editing, especially:
- package.json
- pbiviz.json
- capabilities.json
- src/visual.ts
- src/settings.ts
- src/features.py
- src/simulate.py
- src/model.py
- src/**/*.py
- src/**/*.ts
- explain_driver.py
- main.py
- README.md

Update README.md for:
- setup instructions
- npm/pbiviz commands
- data roles / field wells
- formatting pane options
- visual behaviour
- interactions
- tooltips
- limitations
- troubleshooting
- recent implementation changes

Do not invent features.
Do not document functionality that is not present in the code.
Do not include secrets, internal URLs, or company-private data.

After editing, summarise:
1. README sections changed
2. Code files that drove the README update
3. Anything uncertain that needs manual review