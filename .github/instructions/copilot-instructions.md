# Project AI Instructions

This project should stay well documented.

When editing code:
- Add comments only where they explain intent, business logic, Power BI visual behaviour, data roles, formatting logic, or non-obvious TypeScript.
- Do not add comments that simply repeat what the code says.
- Prefer TSDoc comments for exported classes, public methods, interfaces, settings objects, and complex visual update logic.
- Keep comments short and useful.

When changing functionality:
- Check whether README.md needs updating.
- Update README.md when setup steps, build commands, data roles, capabilities, configuration options, visual behaviour, field wells, formatting settings, or known limitations change.
- Keep README.md practical and developer-facing.
- Include examples where useful.

For Power BI custom visuals:
- Document data roles, capabilities.json changes, formatting pane options, visual interactions, tooltip behaviour, and any DAX/measure assumptions.
- Be careful not to expose company-private data, credentials, tenant IDs, or internal-only URLs.