"""Configuration management."""

import logging
from pathlib import Path

import yaml

from auto_improvement.models import Config

logger = logging.getLogger(__name__)


def save_config(config: Config, config_path: Path) -> None:
    """Save configuration to YAML file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)

    def _replace_types(obj: object) -> object:
        """Recursively replace class/type objects with import path strings for YAML serialization."""
        if isinstance(obj, dict):
            return {k: _replace_types(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_replace_types(v) for v in obj]
        # Replace classes/types (including ABCMeta instances) with module.qualname
        try:
            import types

            if isinstance(obj, type | types.GenericAlias):
                return f"{obj.__module__}.{obj.__qualname__}"
        except Exception as e:
            logger.debug(f"Could not serialize type object: {e}")
        return obj

    # Exclude client class objects from model_dump so Pydantic does not attempt
    # to serialize runtime class objects (which use ABCMeta and are not JSON-serializable).
    exclude = {
        "agent_config": {"client"},
        "issue_tracker": {"client"},
        "version_control_config": {"client"},
    }
    data = config.model_dump(mode="json", exclude=exclude)

    # Ensure all non-serializable objects (like class objects / ABCMeta) are turned
    # into strings by going through JSON with a safe `default` handler, then
    # loading back to Python for YAML dumping.
    import json

    def _json_default(o: object) -> str:
        try:
            # For classes/types, use full import path
            if isinstance(o, type):
                return f"{o.__module__}.{o.__qualname__}"
            return str(o)
        except Exception as e:
            logger.debug(f"JSON serialization fallback for {type(o)}: {e}")
            return str(type(o))

    json_text = json.dumps(data, default=_json_default)
    safe_data = json.loads(json_text)

    with open(config_path, "w") as f:
        yaml.dump(safe_data, f, default_flow_style=False, sort_keys=False)
