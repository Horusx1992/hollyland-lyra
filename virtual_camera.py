"""Discover only our named v4l2loopback node and attach a bounded output branch."""
from pathlib import Path

LABEL = 'Lyra Control'


def find_device(sysfs=Path('/sys/class/video4linux')):
    found = []
    for entry in sysfs.glob('video*'):
        try:
            if (entry/'name').read_text().strip() == LABEL and '/devices/virtual/video4linux/' in str(entry.resolve()):
                found.append('/dev/'+entry.name)
        except FileNotFoundError:
            continue
    if len(found) > 1:
        raise RuntimeError('Multiple virtual cameras are named Lyra Control. Check the system configuration.')
    return found[0] if found else None


def add_output(pipeline, sink, device):
    """Both consumers receive the same rotated/cropped/filtered video."""
    from gi.repository import Gst
    if device != find_device():
        raise RuntimeError('The Lyra Control virtual output is unavailable.')
    upstream = sink.get_static_pad('sink').get_peer().get_parent_element()
    upstream.unlink(sink)
    tee = Gst.ElementFactory.make('tee', 'output_tee')
    preview_queue = Gst.ElementFactory.make('queue', 'preview_queue')
    output_queue = Gst.ElementFactory.make('queue', 'output_queue')
    convert = Gst.ElementFactory.make('videoconvert', 'output_convert')
    caps = Gst.ElementFactory.make('capsfilter', 'output_caps')
    writer = Gst.ElementFactory.make('v4l2sink', 'virtual_output')
    elements = [tee, preview_queue, output_queue, convert, caps, writer]
    if any(item is None for item in elements):
        raise RuntimeError('Required GStreamer virtual-output plugins are unavailable.')
    for queue in (preview_queue, output_queue):
        queue.set_property('max-size-buffers', 2)
        queue.set_property('max-size-bytes', 0)
        queue.set_property('max-size-time', 0)
        queue.set_property('leaky', 2)
    caps.set_property('caps', Gst.Caps.from_string('video/x-raw,format=YUY2'))
    writer.set_property('device', device)
    writer.set_property('sync', False)
    for element in elements:
        pipeline.add(element)
    for chain in ((upstream, tee), (tee, preview_queue, sink),
                  (tee, output_queue, convert, caps, writer)):
        for first, second in zip(chain, chain[1:]):
            if not first.link(second):
                raise RuntimeError('Could not link the virtual camera output.')
