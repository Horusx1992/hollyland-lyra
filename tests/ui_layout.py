"""Opt-in read-only GTK layout captures. Camera video is never started."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from gi.repository import Gtk, GLib, Gdk

snapshot = (json.loads((app.ROOT/'artifacts/restored-first-setup.json').read_text())
            if '--offline' in sys.argv else app.camera.snapshot())
with patch.object(app.Window, 'refresh'):
    window = app.Window()
window.auto_preview_started = True
window.loaded(snapshot)
root = app.ROOT/'artifacts'
root.mkdir(exist_ok=True)
cases = [('studio-camera', 0, 1360, 840), ('studio-image', 0, 1360, 840),
         ('studio-framing', 1, 1360, 840), ('studio-recording', 2, 1360, 840),
         ('studio-compact', 2, 1040, 660), ('studio-small', 0, 980, 640),
         ('studio-access', 0, 980, 640)]
index = 0
errors = []
records = []


def begin():
    name, page, width, height = cases[index]
    if name == 'studio-access':
        window.camera_unavailable(PermissionError('simulated denied access'))
    window.sidebar.set_current_page(page)
    window.image_expander.set_expanded(name == 'studio-image')
    if name == 'studio-image':
        window.exposure_expander.set_expanded(False)
    else:
        window.exposure_expander.set_expanded(True)
    window.resize(width, height)
    GLib.timeout_add(180, capture)
    return False


def capture():
    global index
    try:
        name, page, requested_width, requested_height = cases[index]
        width, height = window.get_size()
        assert width <= requested_width and height <= requested_height, (name, width, height)
        picture = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, width, height)
        assert picture
        picture.savev(str(root/f'{name}.png'), 'png', [], [])
        records.append({'name': name, 'size': [width, height],
                        'preview_width': window.video.get_allocated_width(),
                        'inspector_width': window.inspector_shell.get_allocated_width()})
        index += 1
        if index == len(cases):
            (root/'studio-layout.json').write_text(json.dumps(records, indent=2)+'\n')
            window.destroy()
            return False
        GLib.timeout_add(80, begin)
        return False
    except Exception as error:
        errors.append(repr(error))
        window.destroy()
        return False


GLib.timeout_add(300, begin)
Gtk.main()
if errors:
    raise RuntimeError(errors)
print('PASS: studio layout captures without camera images', records)
