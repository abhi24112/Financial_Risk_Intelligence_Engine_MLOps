import os
from typing import Any

import yaml


def load_config(config_name: str) -> dict[str, Any]:
    """
    Loads a YAML configuration file from the configs/ directory.
    Args:
        config_name (str): The name of the config file (e.g., 'model.yaml' or 'model')
    Returns:
        Dict[str, Any]: The parsed configuration dictionary.
    """
    if not config_name.endswith(".yaml") and not config_name.endswith(".yml"):
        config_name += ".yaml"

    # Assume the configs folder is at the root of the project
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "configs", config_name)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config
