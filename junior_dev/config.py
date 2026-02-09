from pathlib import Path
from typing import Optional, Dict, Any
import yaml


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    if config_path is None:
        return {}
    
    config_path = Path(config_path)
    if not config_path.exists():
        return {}
    
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def get_config_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    keys = key_path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value if value is not None else default

