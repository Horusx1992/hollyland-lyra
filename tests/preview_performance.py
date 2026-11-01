"""Opt-in preview pacing check. Stores timings only, never camera images."""
import argparse
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from video_preview import Preview, Gst, Gtk, GLib
from camview.pipeline import PipelineBuilder

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--synthetic', action='store_true')
args = parser.parse_args()
build = PipelineBuilder.build


def synthetic_build(builder):
    pipeline = build(builder)
    source = pipeline.get_by_name('source')
    caps = pipeline.get_by_name('capsfilter')
    source.unlink(caps)
    pipeline.remove(source)
    synthetic = Gst.ElementFactory.make('videotestsrc')
    synthetic.set_property('is-live', True)
    pipeline.add(synthetic)
    assert synthetic.link(caps)
    return pipeline


window = Gtk.Window()
window.set_default_size(920, 600)
preview = Preview(lambda *_: None)
native_times = []
display_times = []
draw_times = []
present_times = []
original_sample = preview.native_sample
original_display = preview.new_sample
original_present = preview.present_frame
last_frame = None


def sample(sink):
    result = original_sample(sink)
    native_times.append(time.monotonic())
    return result


def display_sample(sink):
    result = original_display(sink)
    display_times.append(time.monotonic())
    return result


def drawn(*_):
    global last_frame
    if preview.frame is not None and preview.frame is not last_frame:
        draw_times.append(time.monotonic())
        last_frame = preview.frame


def present(*args):
    present_times.append(time.monotonic())
    return original_present(*args)


preview.native_sample = sample
preview.new_sample = display_sample
preview.present_frame = present
preview.connect_after('draw', drawn)
window.add(preview)
window.show_all()
node = '/dev/video999' if args.synthetic else app.video_device()
with patch.object(PipelineBuilder, 'build', synthetic_build if args.synthetic else build):
    preview.start(node, '1080p · 60 fps')
started = time.monotonic()
failure = []
result = {}


def finish():
    try:
        end = time.monotonic()
        begin = started + 1
        duration = end - begin
        native = [t for t in native_times if begin <= t <= end]
        draws = [t for t in draw_times if begin <= t <= end]
        result.update(source='synthetic' if args.synthetic else 'Lyra',
                      backend=window.get_display().__gtype__.name,
                      native_fps=len(native)/duration, preview_fps=len(draws)/duration,
                      display_branch_fps=len([t for t in display_times if begin <= t <= end])/duration,
                      max_draw_gap_ms=max((b-a for a, b in zip(draws, draws[1:])), default=0)*1000,
                      ticks_per_second=len([t for t in present_times if begin <= t <= end])/duration,
                      native_size=[preview.capture.width, preview.capture.height])
        assert result['native_fps'] > 50, result
        assert result['preview_fps'] >= result['native_fps'] * .8, result
    except Exception as error:
        failure.append(str(error))
    finally:
        preview.stop()
        window.destroy()
        Gtk.main_quit()
    return False


GLib.timeout_add(4500, finish)
Gtk.main()
print(json.dumps(result, indent=2))
if failure:
    raise SystemExit('FAIL: ' + '; '.join(failure))
name = f"preview-pacing-{result['backend']}-{result['source']}.json"
(app.ROOT/'artifacts'/name).write_text(json.dumps(result, indent=2)+'\n')
print('PASS: 60fps preview follows source cadence without a 30fps ceiling')
