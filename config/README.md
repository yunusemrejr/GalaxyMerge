# Public Config Examples

These files are safe examples for the public repository. They intentionally use
placeholder provider IDs, placeholder model names, and `example.invalid` URLs.

For local development, copy the examples into a local-only config directory and
fill them with environment-variable names only:

```bash
mkdir -p config_templates
cp config/providers.example.json config_templates/providers.json
cp config/models.example.json config_templates/models.json
cp config/fusion.example.json config_templates/fusion.json
cp config/routing.example.json config_templates/routing.json
```

Never commit filled provider configs, endpoint lists, API keys, tokens, or
machine-local routing choices. Real API keys must live in exported environment
variables or ignored user-local files.
