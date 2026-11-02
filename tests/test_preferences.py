import preferences


def test_saved_rotation_and_invalid_config_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    assert preferences.load_rotation() == 0
    preferences.save_rotation(270)
    assert preferences.load_rotation() == 270
    preferences.config_path().write_text('{"rotation": 45}')
    assert preferences.load_rotation() == 0
    preferences.config_path().write_text('[]')
    assert preferences.load_rotation() == 0


def test_recording_choices_do_not_erase_orientation(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    preferences.save_rotation(90)
    preferences.save_option('microphone', 'usb-mic')
    preferences.save_option('record_folder', '/tmp/My Videos')
    preferences.save_option('startup_camera_profile', 'medium-light')
    preferences.save_rotation(270)
    assert preferences.load_rotation() == 270
    assert preferences.load_option('microphone', 'default') == 'usb-mic'
    assert preferences.load_option('record_folder', '') == '/tmp/My Videos'
    assert preferences.load_option('startup_camera_profile', 'none') == 'medium-light'
