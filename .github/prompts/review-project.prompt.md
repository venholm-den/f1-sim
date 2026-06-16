---

name: review-project
description: Review the current project and suggest improvements, removable files, and new data connections.
agent: Project Reviewer & Data Scout
------------------------------------

Review this repository as a full project.

Focus on:

* code quality
* project structure
* simulation logic
* data loading
* FastF1 usage
* OpenF1 usage
* FIA document integration
* weather modelling
* fantasy scoring
* visual/report generation
* README accuracy
* useful new data connections
* files that may be safe to remove, archive, ignore, or consolidate

Do not edit source files, config files, tests, documentation, or outputs.

The only file you may create or overwrite is the review report:

`outputs/reviews/project_review.txt`

If the folder does not exist, create it.

Inspect the relevant files before answering, especially:

* README.md
* requirements.txt
* pyproject.toml
* package.json
* src/**/*.py
* src/**/*.ts
* scripts/**/*.py
* tests/**/*.py
* outputs/**/*.json
* outputs/**/*.csv
* config files
* any existing data-source modules
* generated artifacts
* old scripts
* duplicate files
* unused files
* temporary/debug files
* stale output files
* manual data files that are now replaced by automated data loading

When checking for removable files:

* Do not delete anything.
* Separate files into:

  * Safe to remove
  * Probably remove after confirmation
  * Archive instead of delete
  * Keep
* Explain why each file is listed.
* Mention any risk of deleting it.
* Suggest `.gitignore` additions where appropriate.
* Identify duplicate or superseded files.
* Identify files that look generated and should not be committed.
* Identify manual data files that have been replaced by automated FastF1/OpenF1/backtest logic.
* Identify stale outputs that should be regenerated rather than stored.

Return the review using the Project Reviewer & Data Scout output format.

Also write the full findings to:

`outputs/reviews/project_review.txt`

The report should include these sections:

1. Executive summary
2. Project health score
3. Highest-impact improvements
4. Code quality review
5. Project structure review
6. Simulation logic review
7. Data loading review
8. FastF1 usage review
9. OpenF1 usage review
10. FIA document integration review
11. Weather modelling review
12. Fantasy scoring review
13. Visual/report generation review
14. README/documentation accuracy review
15. Removable / stale / duplicate file review
16. Suggested `.gitignore` additions
17. Useful new data connections
18. Recommended GitHub issues to create
19. Suggested next steps

For recommended GitHub issues, include:

* issue title
* priority
* why it matters
* affected files
* suggested acceptance criteria

For removable files, use this table format:

| File | Recommendation | Reason | Risk | Action |
| ---- | -------------- | ------ | ---- | ------ |

Do not make code changes.
Do not delete files.
Do not commit anything.
