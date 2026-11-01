from unittest.mock import patch
import gi
import pytest
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
import app


def test_new_workspace_uses_native_4k_instead_of_silent_720p_default(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    if not Gtk.init_check()[0]:pytest.skip('GTK display required')
    with patch.object(app.Window,'refresh'),patch.object(app.Window,'refresh_microphones'),\
         patch.object(app.preferences,'load_option',side_effect=lambda name,default:default),\
         patch.object(Gtk,'main_quit'):
        window=app.Window()
        try:
            assert window.mode_choice.get_active_text()=='4K · 30 fps','A new session silently starts recording from a 720p capture'
        finally:
            window.destroy()
