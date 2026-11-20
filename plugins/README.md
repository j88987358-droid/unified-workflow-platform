# Plugin Directory

New integrations should be added as independent plugins.

Each plugin must provide a plugin.json manifest containing:
- id
- name
- version
- api_version
- entry_point
- enabled
- dependencies

The core discovers manifests dynamically.
Plugin code must be reviewed and approved before execution.
