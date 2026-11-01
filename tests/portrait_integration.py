"""Opt-in camera + independent virtual-camera consumer, without saving images."""
from pathlib import Path
import json
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import video_device
from video_preview import Preview, Gst, Gtk, GLib, GstVideo
import virtual_camera

node = virtual_camera.find_device()
assert node, 'Set up the named virtual camera first'
window = Gtk.Window()
preview = Preview(lambda text, playing: print(text, flush=True))
window.add(preview)
window.show_all()
preview.rotation = 90
preview.output_device = node
preview.start(video_device(), '1080p · 30 fps')
consumer = None
step = 0
started = time.monotonic()
records = []
errors = []


def tick():
    global consumer, step
    try:
        assert time.monotonic()-started < 35, 'Portrait output timed out'
        assert preview.running, preview.message
        if preview.frames_received < 5:
            return True
        expected = [(1080,1920),(1080,1920),(1080,1080),(1920,1080)][step]
        native = GstVideo.VideoInfo.new_from_caps(preview.last_caps)
        assert (native.width,native.height) == expected
        if consumer is None:
            consumer = Gst.parse_launch(f'v4l2src device={node} ! video/x-raw,format=YUY2 ! appsink name=reader sync=false max-buffers=1 drop=true')
            assert consumer.set_state(Gst.State.PLAYING) != Gst.StateChangeReturn.FAILURE
            return True
        failure = consumer.get_bus().pop_filtered(Gst.MessageType.ERROR)
        if failure:
            raise RuntimeError(failure.parse_error())
        sample = consumer.get_by_name('reader').emit('try-pull-sample', 0)
        if sample is None:
            return True
        structure = sample.get_caps().get_structure(0)
        size = (structure.get_value('width'),structure.get_value('height'))
        assert size == expected, size
        records.append({'rotation':preview.rotation, 'mirror':preview.mirror,'shape':preview.shape,
                        'preview':list(expected),'independent_consumer':list(size),
                        'frames_received':preview.frames_received})
        consumer.set_state(Gst.State.NULL)
        consumer = None
        previous = preview.pipeline
        step += 1
        if step == 1:
            preview.set_mirror(True)
            preview.set_rotation(270)
        elif step == 2:
            preview.set_shape('circle')
        elif step == 3:
            preview.set_shape('rectangle')
            preview.set_rotation(0)
        else:
            preview.set_output_device(None)
            assert previous.get_state(0).state == Gst.State.NULL
            preview.stop()
            window.destroy()
            Gtk.main_quit()
            return False
        assert previous.get_state(0).state == Gst.State.NULL
        return True
    except Exception as error:
        errors.append(repr(error))
        if consumer:
            consumer.set_state(Gst.State.NULL)
        preview.stop()
        window.destroy()
        Gtk.main_quit()
        return False


GLib.timeout_add(150,tick)
Gtk.main()
if errors:
    raise RuntimeError(errors)
(Path(__file__).resolve().parents[1]/'artifacts/portrait-validation.json').write_text(
    json.dumps({'output':node,'cases':records,'pipeline_released':True},indent=2)+'\n')
print('PASS:',records)
