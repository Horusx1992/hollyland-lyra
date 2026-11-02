import copy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import app
import lyra_backend as camera


def state():
    values = {name: {'cur': 0, 'min': -100, 'max': 100, 'step': 1,
                     'isAuto': 2, 'enable': 1, 'def': 99}
              for name in camera.IMAGE_SETTINGS}
    values['anti-flicker'].update(cur=0, list=['OFF', '50Hz', '60Hz'])
    values['shutter'].update(cur=0, list=['1/60', '1/100'], isAuto=0)
    values['iso'].update(cur=0, list=['100', '250', '400'], isAuto=0)
    values['white-balance'].update(cur=5100, min=2800, max=7000, isAuto=0)
    return values


def test_medium_profile_resolves_changed_shutter_list_and_keeps_iso_awb_auto():
    values = state()
    def read(name):
        return {'module': 'C4502'} if name == 'info' else copy.deepcopy(values[name])
    def apply(name, value, automatic=False):
        camera.validate(name, value, values[name], automatic)
        if name == 'anti-flicker' and values[name]['list'][value] == '50Hz':
            values['shutter'].update(cur=0, list=['1/100', '1/50'], isAuto=2)
        values[name]['cur'] = value
        if values[name]['isAuto'] != 2:
            values[name]['isAuto'] = 0 if automatic else 1
        return copy.deepcopy(values[name])
    with patch.object(camera, 'read', side_effect=read), \
         patch.object(camera, 'apply', side_effect=apply) as write, \
         patch.object(camera, 'snapshot', return_value={}):
        result = camera.apply_medium_light_profile()
    assert len(result['settings']) == 8
    assert not result['skipped']
    assert values['shutter']['list'][values['shutter']['cur']] == '1/100'
    assert values['iso']['isAuto'] == values['white-balance']['isAuto'] == 0
    assert values['contrast']['cur'] == values['saturation']['cur'] == values['brightness']['cur'] == 0
    assert values['sharpness']['cur'] == 50
    assert not any(call.args[0] in ('zoom', 'focus-mode') for call in write.call_args_list)


def test_medium_profile_rolls_back_when_firmware_cannot_supply_1_100():
    values = state()
    values['shutter']['list'] = ['1/60', '1/120']
    def read(name):
        return {'module': 'C4502'} if name == 'info' else copy.deepcopy(values[name])
    with patch.object(camera, 'read', side_effect=read), \
         patch.object(camera, 'apply'), patch.object(camera, 'restore_image_state') as restore:
        with pytest.raises(camera.CameraError, match='Previous image settings restored'):
            camera.apply_medium_light_profile()
    restore.assert_called_once_with(values)


def test_selected_startup_profile_applies_once_then_refresh_only_reads():
    window = SimpleNamespace(startup_profile_pending=True)
    with patch.object(camera, 'apply_medium_light_profile', return_value={'snapshot': {'settings': {}}}) as apply, \
         patch.object(camera, 'snapshot', return_value={'settings': {}}) as read:
        assert app.Window.load_camera_settings(window)['applied_profile'] == 'Medium light'
        app.Window.load_camera_settings(window)
    apply.assert_called_once()
    read.assert_called_once()
    assert not window.startup_profile_pending


def test_denied_startup_keeps_profile_pending_for_authorization_retry():
    window = SimpleNamespace(startup_profile_pending=True)
    with patch.object(camera, 'apply_medium_light_profile', side_effect=PermissionError('denied')):
        with pytest.raises(PermissionError):
            app.Window.load_camera_settings(window)
    assert window.startup_profile_pending


def test_no_selected_profile_does_not_write_camera_settings():
    window = SimpleNamespace(startup_profile_pending=False)
    with patch.object(camera, 'apply_medium_light_profile') as apply, patch.object(camera, 'snapshot') as read:
        app.Window.load_camera_settings(window)
    apply.assert_not_called()
    read.assert_called_once()
