"""Verified native Lyra settings; no GTK or vendor SDK dependency."""
import json
import math
import os
import secrets
import threading
from pathlib import Path

import lyra_probe as wire

SETTINGS = {
    'zoom': 'Camera zoom', 'white-balance': 'White balance', 'shutter': 'Shutter speed',
    'iso': 'ISO', 'anti-flicker': 'Anti-flicker',
    'brightness': 'Brightness', 'contrast': 'Contrast', 'saturation': 'Saturation',
    'sharpness': 'Sharpness', 'focus-mode': 'Focus mode',
}
WRITABLE = frozenset(SETTINGS) - {'focus-mode'}
IMAGE_SETTINGS = tuple(name for name in SETTINGS if name not in ('zoom', 'focus-mode'))
_lock = threading.RLock()


class CameraError(RuntimeError):
    pass


def read(name):
    with _lock:
        request = wire.request_for(name, secrets.randbelow(10001))
        result = wire.probe(wire.find_device(), request,
                            wire.encode_request(request, secrets.randbelow(10001)), 2)
        response = result['matched_response']
        if response is None:
            raise CameraError('The camera did not respond. Check its connection and try again.')
        command = wire.COMMANDS[name][0]
        data = [item for item in response.get('data', []) if item.get('cmd') == command]
        if len(data) != 1 or data[0].get('state', 0) != 0:
            raise CameraError('The camera rejected the setting query.')
        return data[0]


def snapshot():
    with _lock:
        info = read('info')
        values = {name: read(name) for name in SETTINGS}
        return {'info': info, 'settings': values}


def initial_profile():
    return load_profile('initial_camera_profile.json')


def medium_light_profile():
    return load_profile('medium_light_profile.json')


def load_profile(filename):
    profile = json.loads((Path(__file__).parent/filename).read_text())
    if profile.get('schema') != 1 or set(profile.get('settings', {})) != set(IMAGE_SETTINGS):
        raise CameraError('The camera profile is invalid.')
    for name, entry in profile['settings'].items():
        if set(entry) != {'value', 'automatic'} or not isinstance(entry['automatic'], bool):
            raise CameraError(f'Invalid profile setting: {name}')
        if not isinstance(entry['value'], (str, int, float)):
            raise CameraError(f'Invalid profile value: {name}')
    return profile


def profile_value(name, setting, entry):
    value = entry['value']
    if 'list' in setting:
        options = [str(item) for item in setting['list']]
        if str(value) not in options:
            raise CameraError(f'{SETTINGS[name]} no longer supports the profile value {value}.')
        value = options.index(str(value))
    return validate(name, value, setting, entry['automatic'])


def restore_image_state(state):
    """Restore a snapshot in dependency order, mapping lists by their text."""
    order = ('anti-flicker',) + tuple(name for name in IMAGE_SETTINGS if name != 'anti-flicker')
    for name in order:
        old = state[name]
        if old.get('enable') != 1:
            continue
        value = old['list'][int(old['cur'])] if 'list' in old else old['cur']
        current = read(name)
        entry = {'value': value, 'automatic': old.get('isAuto') == 0}
        resolved = profile_value(name, current, entry)
        apply(name, resolved, entry['automatic'])


def reset_image_defaults():
    """Restore the first verified profile, including Auto; never trust mutable def."""
    return apply_image_profile(initial_profile())


def apply_medium_light_profile():
    return apply_image_profile(medium_light_profile())


def apply_image_profile(profile):
    """Apply a bundled image profile with capability readback and rollback."""
    with _lock:
        if read('info').get('module') != profile['model']:
            raise CameraError('The image profile does not match this camera model.')
        before = {name: read(name) for name in IMAGE_SETTINGS}
        order = ('anti-flicker',) + tuple(name for name in IMAGE_SETTINGS if name != 'anti-flicker')
        applied = {}
        skipped = []
        try:
            for name in order:
                setting = read(name)
                if setting.get('enable') != 1:
                    skipped.append(name)
                    continue
                entry = profile['settings'][name]
                value = profile_value(name, setting, entry)
                # Establish the profile's remembered manual value before Auto.
                # This also restores the firmware's remembered manual baseline.
                if entry['automatic']:
                    apply(name, value, False)
                applied[name] = apply(name, value, entry['automatic'])
        except Exception as error:
            try:
                restore_image_state(before)
                rollback = 'Previous image settings restored.'
            except Exception as restore_error:
                rollback = f'Could not fully restore previous settings: {restore_error}'
            raise CameraError(f'Image profile stopped at {SETTINGS[name]}. {rollback} {error}') from error
        return {'settings': applied, 'skipped': skipped, 'mode_changes': [], 'snapshot': snapshot()}


def validate(name, value, setting, automatic):
    if name not in WRITABLE or setting.get('enable', 0) != 1:
        raise CameraError('This setting is currently read-only.')
    if not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Invalid value.')
    if automatic and setting.get('isAuto', 2) == 2:
        raise ValueError('Auto mode is unavailable for this setting.')
    if 'list' in setting:
        if int(value) != value or not 0 <= value < len(setting['list']):
            raise ValueError('Invalid selection.')
        return int(value)
    minimum, maximum, step = (setting[key] for key in ('min', 'max', 'step'))
    if not all(math.isfinite(n) for n in (minimum, maximum, step)) or step <= 0:
        raise CameraError('The camera reported invalid setting limits.')
    if not minimum-1e-7 <= value <= maximum+1e-7:
        raise ValueError('Value is outside the supported range.')
    nearest = minimum + round((value-minimum)/step)*step
    if not math.isclose(value, nearest, rel_tol=0, abs_tol=1e-5):
        raise ValueError('Value does not match the supported step.')
    # Round away only binary-float noise in e.g. a vendor-reported 0.1 step.
    return float(value)


def encode_set(name, value, flag, request_id, message_id):
    if name not in WRITABLE or flag not in (0, 1, 2) or not math.isfinite(value):
        raise ValueError('Unsupported setting or value.')
    cmd, description = wire.COMMANDS[name]
    request = {'id': request_id, 'type': 0, 'data': [
        {'cmd': cmd, 'cmdDes': description, 'cur': value, 'isAuto': flag}]}
    payload = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode()
    if len(payload) > wire.REPORT_SIZE-wire.HEADER.size:
        raise ValueError('Oversized setting packet.')
    return (wire.HEADER.pack(5, message_id, 1, 0)+payload).ljust(wire.REPORT_SIZE, b'\0')


def apply(name, value, automatic=False):
    with _lock:
        before = read(name)
        value = validate(name, value, before, automatic)
        flag = 0 if automatic else (2 if before.get('isAuto', 2) == 2 else 1)
        frame = encode_set(name, value, flag, secrets.randbelow(10001), secrets.randbelow(10001))
        # The camera does not acknowledge every SET. Never resend a SET blindly;
        # use independent GETs to confirm what the device actually applied.
        device = wire.find_device()
        fd = os.open(device, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            if os.write(fd, frame) != len(frame):
                raise CameraError('The complete setting packet could not be sent.')
        finally:
            os.close(fd)
        after = read(name)
        if automatic:
            verified = after.get('isAuto') == 0
        else:
            verified = math.isclose(after.get('cur', math.nan), value, rel_tol=0, abs_tol=1e-5)
            if flag != 2:
                verified = verified and after.get('isAuto') == flag
        if not verified:
            raise CameraError('The camera did not confirm the requested value. Refresh to read its state.')
        return after
