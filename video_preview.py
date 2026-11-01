"""In-process GTK video view, backed by the bundled camview pipeline.

Native YUV samples feed the recorder independently of GTK. A separate, bounded
display branch scales before RGB conversion so GUI painting never maps full
4K RGB frames. Wayland and X11 share the same in-process rendering path.
"""
import math
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gst, GstVideo, Gtk, PangoCairo

from camview import effects
from camview.config import CaptureConfig, PixelFormat
from camview.geometry import Rect, centered_crop, crop_borders
from camview import pipeline as video
import virtual_camera
from recording import Recorder

Gst.init(None)
MODES = {
    '720p · 30 fps': (1280, 720, 30, PixelFormat.NV12),
    '1080p · 30 fps': (1920, 1080, 30, PixelFormat.NV12),
    '1080p · 60 fps': (1920, 1080, 60, PixelFormat.NV12),
    '4K · 30 fps': (3840, 2160, 30, PixelFormat.MJPG),
}
SHAPES = {'rectangle': 'Full frame', 'rounded': 'Rounded', 'circle': 'Circle', 'phone': 'Portrait crop · 9:16'}


class Preview(Gtk.DrawingArea):
    def __init__(self, on_status):
        super().__init__()
        self.set_size_request(400, 280)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_direction(Gtk.TextDirection.LTR)
        self.on_status = on_status
        self.pipeline = self.sink = self.frame = None
        self.display_filter = None
        self.display_size = None
        self.capture = None
        self.effect = effects.NORMAL
        self.shape = 'rectangle'
        self.mirror = False
        self.rotation = 0
        self.output_device = None
        self.software_zoom = 1.0
        self.frames_received = 0
        self.frames_drawn = 0
        self.recorder = Recorder()
        self.last_caps = self.latest_sample = None
        self.sample_lock = threading.Lock()
        self.message = 'Start the preview to see your camera here'
        self.timer = 0
        self.connect('draw', self.draw_frame)
        self.connect('size-allocate', lambda *_: self.update_display_size())
        self.connect('destroy', lambda *_: self.stop())

    @property
    def running(self):
        return self.pipeline is not None

    def view_size(self):
        width, height = self.oriented_size()
        if self.shape == 'phone':
            crop = centered_crop(width, height, (9, 16))
        elif self.shape == 'circle':
            crop = centered_crop(width, height, (1, 1))
        else:
            crop = Rect(0, 0, width, height)
        return crop.width, crop.height

    def oriented_size(self):
        width, height = (self.capture.width, self.capture.height) if self.capture else (1280, 720)
        return (height, width) if self.rotation in (90, 270) else (width, height)

    def borders(self):
        source_width, source_height = self.oriented_size()
        width, height = self.view_size()
        crop = Rect((source_width-width)//2, (source_height-height)//2, width, height)
        return crop_borders(source_width, source_height, crop)

    def start(self, node, mode='720p · 30 fps'):
        self.require_idle_recording()
        self.stop()
        width, height, fps, pixel_format = MODES[mode]
        self.capture = CaptureConfig(node, width, height, fps, pixel_format)
        try:
            builder = (video.PipelineBuilder().with_capture(self.capture)
                .with_sink('appsink').with_rotation(self.rotation)
                .with_mirror(self.mirror).with_effect(self.effect, optimize_neutral=True)
                .with_crop(self.borders()))
            if self.software_zoom != 1:
                builder.with_viewport(*self.view_size(), self.software_zoom)
            self.pipeline = builder.build()
            self.sink = self.pipeline.get_by_name(video.SINK_ELEMENT)
            # Keep the full-resolution branch in the encoder's native YUV420.
            # Only the small GTK branch needs RGB, avoiding two 4K conversions.
            self.sink.set_property('caps', Gst.Caps.from_string('video/x-raw,format=I420'))
            self.sink.set_property('max-buffers', 1)
            self.sink.set_property('drop', True)
            self.sink.set_property('sync', False)
            self.sink.set_property('wait-on-eos', False)
            self.sink.set_property('emit-signals', True)
            self.sink.connect('new-sample', self.native_sample)
            if self.output_device:
                virtual_camera.add_output(self.pipeline, self.sink, self.output_device)
            self.add_display_branch()
            self.frames_received = 0
            self.frames_drawn = 0
            self.message = 'Opening camera…'
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError('Could not start video. Close other apps using the physical camera.')
            self.timer = GLib.timeout_add(33, self.pull_frame)
            self.queue_draw()
        except Exception:
            self.stop()
            raise

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
        self.pipeline = self.sink = self.frame = None
        self.display_filter = self.display_size = None
        with self.sample_lock:
            self.latest_sample = self.last_caps = None
        self.message = 'Preview stopped'
        self.queue_draw()

    def native_sample(self, sink):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.EOS
        try:
            self.recorder.push(sample)
        except Exception as error:
            self.recorder.failure = str(error)
        with self.sample_lock:
            self.last_caps = sample.get_caps()
        return Gst.FlowReturn.OK

    def new_sample(self, sink):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.EOS
        with self.sample_lock:
            self.latest_sample = sample
        return Gst.FlowReturn.OK

    def add_display_branch(self):
        """Scale only the GUI branch; recording keeps every native-resolution sample."""
        upstream = self.sink.get_static_pad('sink').get_peer().get_parent_element()
        upstream.unlink(self.sink)
        tee = video.PipelineBuilder._make(Gst, 'tee', 'display_tee')
        native_queue = video.PipelineBuilder._make(Gst, 'queue', 'native_queue')
        display_queue = video.PipelineBuilder._make(Gst, 'queue', 'display_queue')
        scale = video.PipelineBuilder._make(Gst, 'videoscale', 'display_scale')
        self.display_filter = video.PipelineBuilder._make(Gst, 'capsfilter', 'display_size')
        convert = video.PipelineBuilder._make(Gst, 'videoconvert', 'display_convert')
        sink = video.PipelineBuilder._make(Gst, 'appsink', 'display_sink')
        for queue in (native_queue, display_queue):
            queue.set_property('max-size-buffers', 2)
            queue.set_property('max-size-bytes', 0)
            queue.set_property('max-size-time', 0)
            queue.set_property('leaky', 2)
        for name, value in [('max-buffers', 1), ('drop', True), ('sync', False),
                            ('wait-on-eos', False), ('emit-signals', True)]:
            sink.set_property(name, value)
        sink.set_property('caps', Gst.Caps.from_string('video/x-raw,format=RGB'))
        sink.connect('new-sample', self.new_sample)
        self.update_display_size()
        for element in (tee, native_queue, display_queue, scale, self.display_filter, convert, sink):
            self.pipeline.add(element)
        for chain in ((upstream, tee), (tee, native_queue, self.sink),
                      (tee, display_queue, scale, self.display_filter, convert, sink)):
            for left, right in zip(chain, chain[1:]):
                if not left.link(right):
                    raise RuntimeError('Could not connect the scaled display branch.')

    def update_display_size(self):
        if self.display_filter is None:
            return
        width, height = self.view_size()
        max_width = min(1920, max(2, self.get_allocated_width()))
        max_height = min(1080, max(2, self.get_allocated_height()))
        scale = min(1, max_width/width, max_height/height)
        size = (max(2, int(width*scale)//2*2), max(2, int(height*scale)//2*2))
        if size != self.display_size:
            self.display_filter.set_property('caps', Gst.Caps.from_string(
                f'video/x-raw,width={size[0]},height={size[1]},pixel-aspect-ratio=1/1'))
            self.display_size = size

    def require_idle_recording(self):
        if self.recorder.active:
            raise RuntimeError('Stop recording before changing video settings.')

    def pull_frame(self):
        if self.pipeline is None:
            return False
        bus = self.pipeline.get_bus()
        error = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if error:
            text = 'Camera stream ended.'
            if error.type == Gst.MessageType.ERROR:
                detail, _ = error.parse_error()
                text = f'Video error: {detail.message}'
                if self.output_device:
                    text += ' Close the virtual camera in other apps, then restart the preview.'
            self.timer = 0
            self.stop()
            self.message = text
            self.on_status(text, False)
            return False
        with self.sample_lock:
            sample = self.latest_sample
            self.latest_sample = None
        if sample is not None:
            info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
            buffer = sample.get_buffer()
            success, mapping = buffer.map(Gst.MapFlags.READ)
            if success:
                try:
                    data = GLib.Bytes.new(mapping.data)
                    self.frame = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB,
                        False, 8, info.width, info.height, info.stride[0])
                finally:
                    buffer.unmap(mapping)
                self.frames_received += 1
                if self.frames_received == 1:
                    self.on_status('Live preview connected.', True)
                self.queue_draw()
        return True

    def set_effect(self, effect_id):
        self.require_idle_recording()
        effect = effects.by_id(effect_id)
        rebuild = effect.element != self.effect.element or ((effect == effects.NORMAL) != (self.effect == effects.NORMAL))
        self.effect = effect
        if self.pipeline:
            if rebuild:
                capture = self.capture
                mode = next(name for name, values in MODES.items()
                            if values == (capture.width, capture.height, capture.fps, capture.pixel_format))
                self.start(capture.device, mode)
            else:
                video.apply_effect(self.pipeline, effect)

    def set_mirror(self, enabled):
        self.require_idle_recording()
        self.mirror = enabled
        if self.pipeline:
            self.pipeline.get_by_name(video.FLIP_ELEMENT).set_property('method',
                'horizontal-flip' if enabled else 'none')

    def restart(self):
        if self.running:
            capture = self.capture
            mode = next(name for name, values in MODES.items()
                        if values == (capture.width, capture.height, capture.fps, capture.pixel_format))
            self.start(capture.device, mode)

    def set_rotation(self, degrees):
        self.require_idle_recording()
        if degrees not in (0, 90, 180, 270):
            raise ValueError('Rotation must be 0, 90, 180 or 270')
        self.rotation = degrees
        self.restart()
        self.queue_draw()

    def set_output_device(self, node):
        self.require_idle_recording()
        if node is not None and node != virtual_camera.find_device():
            raise ValueError('Only the named Lyra Control virtual camera is allowed')
        self.output_device = node
        self.restart()

    def set_shape(self, shape):
        self.require_idle_recording()
        if shape not in SHAPES:
            raise ValueError('Unknown preview shape')
        previous_size = self.view_size()
        self.shape = shape
        if self.output_device and self.view_size() != previous_size:
            self.restart()
        else:
            self.update_viewport()

    def set_software_zoom(self, zoom):
        self.require_idle_recording()
        if not 0.25 <= zoom <= 4:
            raise ValueError('Software zoom must be between 0.25 and 4')
        rebuild = (zoom == 1) != (self.software_zoom == 1)
        self.software_zoom = zoom
        if rebuild:
            self.restart()
        else:
            self.update_viewport()

    def update_viewport(self):
        if self.pipeline:
            video.apply_crop(self.pipeline, self.borders())
            video.apply_viewport(self.pipeline, *self.view_size(), self.software_zoom)
            self.update_display_size()
        self.queue_draw()

    def draw_frame(self, widget, ctx):
        width, height = self.get_allocated_width(), self.get_allocated_height()
        ctx.set_source_rgb(0.045, 0.055, 0.075)
        ctx.paint()
        if self.frame is None:
            layout = self.create_pango_layout(self.message)
            layout.set_width(max(1, width-40)*1024)
            _, text_height = layout.get_pixel_size()
            ctx.set_source_rgb(0.75, 0.8, 0.88)
            ctx.move_to(20, (height-text_height)/2)
            PangoCairo.show_layout(ctx, layout)
            return False
        fw, fh = self.frame.get_width(), self.frame.get_height()
        scale = min(width/fw, height/fh)
        vw, vh = fw*scale, fh*scale
        ctx.save()
        ctx.translate((width-vw)/2, (height-vh)/2)
        if self.shape == 'circle':
            ctx.arc(vw/2, vh/2, min(vw, vh)/2, 0, 2*math.pi)
        elif self.shape in ('rounded', 'phone'):
            radius = min(24, vw/2, vh/2)
            for cx, cy, angle in [(vw-radius,radius,-math.pi/2),
                                  (vw-radius,vh-radius,0), (radius,vh-radius,math.pi/2),
                                  (radius,radius,math.pi)]:
                ctx.arc(cx, cy, radius, angle, angle+math.pi/2)
            ctx.close_path()
        else:
            ctx.rectangle(0, 0, vw, vh)
        ctx.clip()
        ctx.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(ctx, self.frame, 0, 0)
        ctx.paint()
        ctx.restore()
        self.frames_drawn += 1
        return False
