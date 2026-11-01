from unittest.mock import patch
import pytest
import virtual_camera


def node(tmp_path, sysfs, number, virtual=True):
    location = 'devices/virtual/video4linux' if virtual else 'devices/usb/video4linux'
    target = tmp_path/location/f'video{number}'
    target.mkdir(parents=True)
    (target/'name').write_text(virtual_camera.LABEL)
    (sysfs/f'video{number}').symlink_to(target)


def test_discovery_ignores_physical_device_with_matching_name(tmp_path):
    sysfs = tmp_path/'class'
    sysfs.mkdir()
    node(tmp_path, sysfs, 0, virtual=False)
    assert virtual_camera.find_device(sysfs) is None
    node(tmp_path, sysfs, 42)
    assert virtual_camera.find_device(sysfs) == '/dev/video42'
    node(tmp_path, sysfs, 43)
    with pytest.raises(RuntimeError):
        virtual_camera.find_device(sysfs)


def test_output_refuses_arbitrary_physical_camera_before_touching_pipeline():
    with patch.object(virtual_camera, 'find_device', return_value='/dev/video42'):
        with pytest.raises(RuntimeError):
            virtual_camera.add_output(None, None, '/dev/video0')
