"""Remember local UI preferences; never store camera images or credentials."""
import json
import os
from pathlib import Path
import tempfile


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'lyra-control/preview.json'


def load_rotation():
    value = load_option('rotation', 0)
    return value if value in (0, 90, 180, 270) else 0


def load_options():
    try:
        data = json.loads(config_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def load_option(name, default):
    value = load_options().get(name, default)
    return value if isinstance(value, type(default)) else default


def save_rotation(value):
    if value not in (0, 90, 180, 270):
        raise ValueError('Invalid rotation')
    save_option('rotation', value)


def save_option(name, value):
    if name not in ('rotation', 'microphone', 'record_folder', 'capture_mode', 'record_quality', 'startup_camera_profile'):
        raise ValueError('Unknown preference')
    data = load_options()
    data[name] = value
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as temporary:
        json.dump(data, temporary)
    try:
        os.replace(temporary.name, target)
    finally:
        Path(temporary.name).unlink(missing_ok=True)
