"""Studio interaction checks; no camera device, audio capture or video files."""
import copy
import time
from unittest.mock import PropertyMock, patch
import gi
import pytest
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib
import app


def camera_state():
    settings={name:{'cur':0,'min':-100,'max':100,'step':1,'isAuto':2,'enable':1}
              for name in app.camera.SETTINGS}
    settings['zoom'].update(cur=1,min=1,max=4,step=.1)
    settings['white-balance'].update(cur=5100,min=2800,max=7000,isAuto=0)
    settings['shutter']={'cur':0,'list':['1/60','1/120'],'enable':1,'isAuto':0}
    settings['iso']={'cur':0,'list':['250','500'],'enable':1,'isAuto':0}
    settings['anti-flicker']={'cur':0,'list':['OFF','50Hz','60Hz'],'enable':1,'isAuto':2}
    settings['focus-mode']={'cur':0,'list':['AF-C'],'enable':0,'isAuto':2}
    return {'info':{'swVer':'test'},'settings':settings}


@pytest.fixture
def window(tmp_path,monkeypatch):
    if not Gtk.init_check()[0]:pytest.skip('GTK display required')
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    with patch.object(app.Window,'refresh'),patch.object(app.Window,'refresh_microphones'),\
         patch.object(Gtk,'main_quit'):
        instance=app.Window()
        instance.auto_preview_started=True
        instance.loaded(camera_state())
        yield instance
        instance.destroy()


def test_primary_capture_controls_are_reachable_without_opening_a_settings_tab(window):
    assert window.mode_choice.get_ancestor(Gtk.Notebook) is None
    assert window.capture_strip.is_ancestor(window.preview_panel)
    assert window.mirror_check.is_ancestor(window.capture_strip)
    window.set_preview_only(True)
    window.show_recording_settings()
    assert not window.preview_only
    assert window.sidebar.get_current_page()==2
    assert window.inspector_shell.get_visible()


def test_refresh_preserves_disclosure_choices_and_keeps_advanced_rows_available(window):
    window.image_expander.set_expanded(True)
    window.exposure_expander.set_expanded(False)
    data=copy.deepcopy(camera_state())
    data['settings']['contrast']['cur']=10
    window.loaded(data)
    assert window.image_expander.get_expanded()
    assert not window.exposure_expander.get_expanded()
    assert window.rows['contrast'].editor.get_value()==10
    assert len(window.rows)==10


def test_recording_locks_capture_strip_as_well_as_the_inspector(window):
    with patch.object(type(window.video.recorder),'active',new_callable=PropertyMock,return_value=True):
        window.update_record_controls()
        assert not window.capture_strip.get_sensitive()
        assert not window.framing.get_sensitive()
        assert not window.record_quality.get_sensitive()
        assert window.record_button.get_sensitive()
        window.set_preview_only(True)
        assert window.record_bar.get_visible()
    window.update_record_controls()


def test_compact_feedback_retains_full_recovery_text(window):
    message='Could not start recording. Select another microphone and try again. '+('detail '*40)
    window.status.set_text(message)
    assert window.status.get_tooltip_text()==message
    assert window.status.get_style_context().has_class('error')
    window.status.set_text('Saved clip.mp4')
    assert not window.status.get_style_context().has_class('error')


def test_failed_preview_does_not_leave_a_stale_live_badge(window):
    window.video_status('Live preview connected.', True)
    assert not window.placeholder.get_visible()
    assert window.preview_badge.get_style_context().has_class('live')
    def failed():raise RuntimeError('Could not open camera')
    window.video_action(failed)
    assert window.placeholder.get_visible()
    assert window.preview_badge.get_text()=='STOPPED'
    assert not window.preview_badge.get_style_context().has_class('live')


def test_camera_tab_explains_missing_settings_and_recovers(window):
    window.camera_unavailable(PermissionError('denied'))
    assert window.camera_notice.get_visible()
    assert window.access_button.is_ancestor(window.camera_notice)
    assert window.access_button.get_visible()
    assert not window.controls.get_sensitive()
    assert 'access' in window.camera_notice_text.get_text().lower()
    window.loaded(camera_state())
    assert not window.camera_notice.get_visible()
    assert window.controls.get_sensitive()
    assert len(window.rows) == 10


def test_camera_tab_has_an_actionable_state_before_first_connection(tmp_path, monkeypatch):
    if not Gtk.init_check()[0]:
        pytest.skip('GTK display required')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    with patch.object(app.Window, 'refresh'), patch.object(app.Window, 'refresh_microphones'), \
         patch.object(Gtk, 'main_quit'):
        instance = app.Window()
        try:
            assert instance.camera_notice.get_visible()
            assert instance.camera_retry_button.get_visible()
            instance.camera_unavailable(RuntimeError('Camera unplugged'))
            assert 'Camera unplugged' in instance.camera_notice_text.get_text()
            assert instance.camera_retry_button.get_sensitive()
        finally:
            instance.destroy()


def test_real_refresh_callback_recovers_camera_tab_after_denied_access(tmp_path, monkeypatch):
    if not Gtk.init_check()[0]:
        pytest.skip('GTK display required')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    def settle(instance):
        deadline = time.monotonic() + 2
        while instance.busy and time.monotonic() < deadline:
            GLib.MainContext.default().iteration(False)
            time.sleep(.001)
        assert not instance.busy
    with patch.object(app.camera, 'snapshot', side_effect=PermissionError('denied')) as read, \
         patch.object(app.Window, 'refresh_microphones'), patch.object(Gtk, 'main_quit'):
        instance = app.Window()
        instance.auto_preview_started = True
        try:
            settle(instance)
            assert instance.camera_notice.get_visible()
            assert instance.access_button.get_visible()
            assert instance.access_button.is_sensitive()
            assert not instance.controls.is_sensitive()
            read.side_effect = None
            read.return_value = camera_state()
            instance.camera_retry_button.emit('clicked')
            settle(instance)
            assert not instance.camera_notice.get_visible()
            assert instance.controls.is_sensitive()
            assert len(instance.rows) == 10
            instance.show_all()
            assert not instance.camera_notice.get_visible()
        finally:
            instance.destroy()


def test_medium_light_action_remembers_default_and_original_reset_clears_it(window):
    result = {'snapshot': camera_state(), 'settings': {}, 'mode_changes': [], 'skipped': []}
    def submit(task, done, *_args, **_kwargs):
        done(task())
        return True
    window.submit = submit
    with patch.object(app.camera, 'apply_medium_light_profile', return_value=result), \
         patch.object(app.camera, 'reset_image_defaults', return_value=result):
        window.medium_light_button.emit('clicked')
        assert window.profile_check.get_active()
        assert app.preferences.load_option('startup_camera_profile', 'none') == 'medium-light'
        window.reset_button.emit('clicked')
        assert not window.profile_check.get_active()
        assert app.preferences.load_option('startup_camera_profile', '') == 'none'
