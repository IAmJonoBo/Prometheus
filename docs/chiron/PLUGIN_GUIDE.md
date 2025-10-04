# Chiron Plugin System Guide

## Overview

The Chiron plugin system allows third-party developers to extend Chiron's functionality without modifying the core codebase. Plugins can add custom dependency analyzers, packaging hooks, remediation strategies, and more.

## Creating a Plugin

### Basic Plugin Structure

```python
from chiron.plugins import ChironPlugin, PluginMetadata

class MyCustomPlugin(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-custom-plugin",
            version="1.0.0",
            description="My awesome Chiron extension",
            author="Your Name",
            requires=("chiron>=0.1.0",),
        )

    def initialize(self, config: dict) -> None:
        """Initialize the plugin with configuration."""
        self.custom_setting = config.get("custom_setting", "default")
        print(f"Initialized with setting: {self.custom_setting}")

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        print("Cleaning up plugin resources")
```

### Plugin Types

#### 1. Dependency Analyzer Plugin

Extends dependency scanning capabilities:

```python
class CustomDependencyAnalyzer(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="custom-analyzer",
            version="1.0.0",
            description="Custom dependency security analyzer",
        )

    def analyze_package(self, package_name: str, version: str) -> dict:
        """Analyze a package for security issues."""
        # Your custom analysis logic
        return {
            "package": package_name,
            "version": version,
            "issues": [],
        }
```

#### 2. Packaging Hook Plugin

Adds pre/post packaging actions:

```python
class PackagingHookPlugin(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="packaging-hooks",
            version="1.0.0",
            description="Custom packaging lifecycle hooks",
        )

    def pre_packaging(self, context: dict) -> None:
        """Run before packaging starts."""
        print("Running pre-packaging checks...")

    def post_packaging(self, context: dict) -> None:
        """Run after packaging completes."""
        print("Running post-packaging validation...")
```

#### 3. Remediation Strategy Plugin

Provides custom fix strategies:

```python
class CustomRemediationPlugin(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="custom-remediation",
            version="1.0.0",
            description="Custom remediation strategies",
        )

    def can_remediate(self, error: dict) -> bool:
        """Check if this plugin can handle the error."""
        return error.get("type") == "custom_error"

    def remediate(self, error: dict) -> dict:
        """Apply remediation strategy."""
        # Your remediation logic
        return {"status": "fixed", "details": "..."}
```

## Distributing Plugins

### Via Python Package

1. **Create package structure:**

```
my_chiron_plugin/
├── setup.py
├── my_chiron_plugin/
│   ├── __init__.py
│   └── plugin.py
└── README.md
```

2. **Define entry point in setup.py:**

```python
from setuptools import setup

setup(
    name="my-chiron-plugin",
    version="1.0.0",
    packages=["my_chiron_plugin"],
    install_requires=["chiron>=0.1.0"],
    entry_points={
        "chiron.plugins": [
            "my_plugin = my_chiron_plugin.plugin:MyCustomPlugin",
        ],
    },
)
```

3. **Implement the plugin:**

```python
# my_chiron_plugin/plugin.py
from chiron.plugins import ChironPlugin, PluginMetadata

class MyCustomPlugin(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-custom-plugin",
            version="1.0.0",
            description="My awesome extension",
        )

    def initialize(self, config: dict) -> None:
        # Plugin initialization
        pass
```

4. **Install and use:**

```bash
pip install my-chiron-plugin
python -m chiron plugin discover
python -m chiron plugin list
```

## Using Plugins

### Discovery and Registration

**Automatic discovery:**

```bash
# Discover plugins from entry points
python -m chiron plugin discover

# List registered plugins
python -m chiron plugin list
```

**Manual registration in code:**

```python
from chiron.plugins import register_plugin
from my_chiron_plugin import MyCustomPlugin

plugin = MyCustomPlugin()
register_plugin(plugin)
```

### Configuration

Configure plugins via configuration file:

```python
# config.py
plugin_config = {
    "my-custom-plugin": {
        "custom_setting": "value",
        "enabled": True,
    },
}

from chiron.plugins import initialize_plugins
initialize_plugins(plugin_config)
```

### Accessing Plugins

```python
from chiron.plugins import get_plugin

plugin = get_plugin("my-custom-plugin")
if plugin:
    # Use the plugin
    result = plugin.some_method()
```

## Best Practices

### 1. Clear Naming

- Use descriptive plugin names
- Follow naming convention: `company-feature-plugin`
- Example: `acme-security-scanner`

### 2. Version Compatibility

- Specify minimum Chiron version in requires
- Follow semantic versioning
- Document breaking changes

### 3. Error Handling

- Handle errors gracefully in plugin code
- Use logging for debugging
- Don't crash the host application

### 4. Resource Management

- Clean up resources in `cleanup()`
- Don't leak file handles or connections
- Be mindful of memory usage

### 5. Documentation

- Document plugin purpose and usage
- Provide configuration examples
- Include type hints

### 6. Testing

- Test plugin in isolation
- Test integration with Chiron
- Provide sample data for testing

## Example Plugins

### Security Scanner Plugin

```python
from chiron.plugins import ChironPlugin, PluginMetadata
import requests

class SecurityScannerPlugin(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="security-scanner",
            version="1.0.0",
            description="Scans dependencies for security vulnerabilities",
            author="Security Team",
        )

    def initialize(self, config: dict) -> None:
        self.api_key = config.get("api_key")
        self.api_url = config.get("api_url", "https://api.example.com")

    def scan_package(self, package: str, version: str) -> list[dict]:
        """Scan a package for vulnerabilities."""
        response = requests.get(
            f"{self.api_url}/scan",
            params={"package": package, "version": version},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return response.json()
```

### Custom Export Plugin

```python
from chiron.plugins import ChironPlugin, PluginMetadata
import json
from pathlib import Path

class CustomExportPlugin(ChironPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="custom-export",
            version="1.0.0",
            description="Exports data in custom format",
        )

    def export(self, data: dict, output_path: Path) -> None:
        """Export data in custom format."""
        custom_format = self._convert_to_custom_format(data)
        output_path.write_text(json.dumps(custom_format, indent=2))

    def _convert_to_custom_format(self, data: dict) -> dict:
        """Convert to custom format."""
        return {
            "version": "1.0",
            "data": data,
            "metadata": {"exported_by": "custom-export"},
        }
```

## Troubleshooting

### Plugin Not Discovered

**Check entry point configuration:**

```bash
pip show -v my-chiron-plugin | grep Entry-points
```

**Verify plugin is installed:**

```bash
pip list | grep chiron
```

### Plugin Fails to Load

**Check logs:**

```bash
python -m chiron plugin discover --verbose
```

**Verify dependencies:**

```bash
pip check
```

### Configuration Issues

**Validate configuration:**

```python
from chiron.plugins import get_plugin

plugin = get_plugin("my-plugin")
if plugin is None:
    print("Plugin not found or not registered")
```

## API Reference

See `chiron/plugins.py` for complete API documentation:

- `ChironPlugin` - Base plugin class
- `PluginMetadata` - Plugin metadata structure
- `PluginRegistry` - Plugin management
- `register_plugin()` - Register a plugin
- `get_plugin()` - Get a registered plugin
- `list_plugins()` - List all plugins
- `discover_plugins()` - Discover plugins from entry points
- `initialize_plugins()` - Initialize all plugins

## Support

For help with plugin development:

- Check the examples in this guide
- Review the API documentation
- Open an issue on GitHub
- Contact the Chiron team
