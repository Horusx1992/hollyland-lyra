"""Bounded processed-video recording with a selected PulseAudio/PipeWire input."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

# Quantizers apply to the processed 8-bit I420 image, not raw sensor data.
QUALITY_PROFILES = {
    'best': ('Best quality', 'qual', 16),
    'balanced': ('Smaller files', 'qual', 21),
    'lossless': ('Lossless · very large files', 'quant', 0),
}


@dataclass(frozen=True)
class Microphone:
    name: str
    description: str


def microphones():
    result = subprocess.run(['pactl', '-f', 'json', 'list', 'sources'],
                            capture_output=True, text=True, check=True, timeout=4)
    sources = json.loads(result.stdout)
    # Monitor sources capture speaker output; this picker is for microphones.
    return [Microphone(item['name'], item.get('description') or item['name'])
            for item in sources if not item['name'].endswith('.monitor')]


def make(factory, name=None):
    element = Gst.ElementFactory.make(factory, name)
    if element is None:
        raise RuntimeError(f'Missing GStreamer plugin: {factory}. See README dependencies.')
    return element


def chain(pipeline, elements):
    for element in elements:
        pipeline.add(element)
    for left, right in zip(elements, elements[1:]):
        if not left.link(right):
            raise RuntimeError(f'Cannot link recording elements: {left.name} to {right.name}')


class Recorder:
    def __init__(self):
        self.pipeline = self.source = self.audio_source = None
        self.path = None
        self.fd = None
        self.started = 0
        self.frames = 0
        self.audio_enabled = False
        self.peak = 0.0
        self.failure = None
        self.failure_debug = None
        self._accepting = False
        self._lock = threading.Lock()
        self.clock = None
        self.clock_origin = 0
        self.last_pts = -1

    @property
    def active(self):
        return self.pipeline is not None

    def start(self, path, caps, microphone='default', audio_factory='pulsesrc', quality='best'):
        """mic=None records video only; audio_factory is injectable for tests."""
        if self.active:
            raise RuntimeError('A recording is already active.')
        if caps is None:
            raise RuntimeError('Wait for the first preview frame before recording.')
        if quality not in QUALITY_PROFILES:
            raise ValueError('Unknown recording quality.')
        path = Path(path)
        if path.suffix.lower() != '.mp4':
            raise ValueError('Recordings must use the .mp4 extension.')
        # Check plugins before creating a file; fdsink writes only our exclusive fd.
        video_source = make('appsrc', 'record_video')
        convert = make('videoconvert')
        raw_caps = make('capsfilter')
        raw_caps.set_property('caps', Gst.Caps.from_string('video/x-raw,format=I420'))
        encoder = make('x264enc', 'record_encoder')
        encoder.set_property('speed-preset', 'superfast')
        encoder.set_property('tune', 'zerolatency')
        _, mode, quantizer = QUALITY_PROFILES[quality]
        encoder.set_property('pass', mode)
        encoder.set_property('quantizer', quantizer)
        encoder.set_property('key-int-max', 60)
        encoder.set_property('threads', min(8, os.cpu_count() or 4))
        parser = make('h264parse')
        mux = make('mp4mux', 'record_mux')
        # Short fragments preserve already-written media after an interrupted run.
        mux.set_property('fragment-duration', 1000)
        sink = make('fdsink')
        sink.set_property('sync', False)
        pipe = Gst.Pipeline.new('lyra-recording')
        self.path = path
        try:
            chain(pipe, [video_source, convert, raw_caps, encoder, parser])
            pipe.add(mux)
            pipe.add(sink)
            if not parser.link(mux) or not mux.link(sink):
                raise RuntimeError('Cannot connect the MP4 writer.')
            self.audio_source = None
            if microphone is not None:
                audio = make(audio_factory, 'record_audio')
                if audio_factory == 'pulsesrc':
                    if microphone != 'default':
                        audio.set_property('device', microphone)
                else:
                    audio.set_property('is-live', True)
                audio_convert, resample = make('audioconvert'), make('audioresample')
                audio_caps = make('capsfilter')
                audio_caps.set_property('caps', Gst.Caps.from_string('audio/x-raw,rate=48000,channels=2'))
                meter = make('level', 'record_level')
                meter.set_property('interval', 100*Gst.MSECOND)
                audio_encoder, audio_parser = make('avenc_aac'), make('aacparse')
                audio_encoder.set_property('bitrate', 192000)
                queue = make('queue')
                queue.set_property('max-size-time', 2*Gst.SECOND)
                queue.set_property('max-size-bytes', 0)
                chain(pipe, [audio, audio_convert, resample, audio_caps, meter, audio_encoder, audio_parser, queue])
                if not queue.link(mux):
                    raise RuntimeError('Cannot connect the audio track.')
                self.audio_source = audio
            video_source.set_property('caps', caps)
            video_source.set_property('format', Gst.Format.TIME)
            video_source.set_property('is-live', True)
            video_source.set_property('do-timestamp', False)
            video_source.set_property('block', False)
            video_source.set_property('max-buffers', 4)
            video_source.set_property('max-bytes', 0)
            video_source.set_property('leaky-type', 2)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC, 0o600)
            sink.set_property('fd', self.fd)
            self.pipeline, self.source = pipe, video_source
            self.frames, self.peak, self.failure, self.failure_debug = 0, 0.0, None, None
            self.audio_enabled = microphone is not None
            self.quality = quality
            self.started = time.monotonic()
            # Assign the common clock/base explicitly. Appsrc's automatic
            # timestamps can be absent while an audio source is still starting.
            self.clock = Gst.SystemClock.obtain()
            self.clock_origin = self.clock.get_time()
            self.last_pts = -1
            pipe.use_clock(self.clock)
            pipe.set_start_time(Gst.CLOCK_TIME_NONE)
            pipe.set_base_time(self.clock_origin)
            if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError('Could not start recording. Check the selected microphone.')
            self._accepting = True
        except Exception:
            pipe.set_state(Gst.State.NULL)
            self.pipeline = self.source = self.audio_source = None
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
                if path.exists() and path.stat().st_size == 0:
                    path.unlink()
            raise

    def push(self, sample):
        """Called from the video streaming thread; never blocks camera delivery."""
        with self._lock:
            if not self._accepting:
                return
            buffer = sample.get_buffer().copy()
            stamp = max(self.last_pts+1, self.clock.get_time()-self.clock_origin)
            buffer.pts = buffer.dts = stamp
            self.last_pts = stamp
            result = self.source.emit('push-buffer', buffer)
            if result == Gst.FlowReturn.OK:
                self.frames += 1
            elif result not in (Gst.FlowReturn.FLUSHING, Gst.FlowReturn.EOS):
                self.failure = f'Video encoder stopped accepting frames: {result.value_nick}'

    def poll(self):
        if not self.active:
            return
        bus = self.pipeline.get_bus()
        for _ in range(32):
            message = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.ELEMENT)
            if message is None:
                break
            if message.type == Gst.MessageType.ERROR:
                detail, debug = message.parse_error()
                if not self.failure:
                    self.failure = detail.message
                    self.failure_debug = debug
            elif message.get_structure() and message.get_structure().get_name() == 'level':
                peaks = message.get_structure().get_value('rms')
                db = max(peaks) if peaks else -100
                self.peak = min(1.0, 10**(db/20)) if math.isfinite(db) else 0.0
        if self.failure:
            raise RuntimeError(self.failure)

    def finish(self):
        """EOS both tracks, wait for mux finalization, then release all devices."""
        with self._lock:
            if not self.active:
                raise RuntimeError('No recording is active.')
            self._accepting = False
            pipe = self.pipeline
        duration = time.monotonic()-self.started
        success = False
        error = None
        try:
            if self.failure and self.frames == 0:
                raise RuntimeError(f'{self.failure} File: {self.path}')
            self.source.emit('end-of-stream')
            if self.audio_source:
                self.audio_source.send_event(Gst.Event.new_eos())
            message = pipe.get_bus().timed_pop_filtered(15*Gst.SECOND,
                Gst.MessageType.EOS | Gst.MessageType.ERROR)
            if message is None:
                error = 'Recording finalization timed out; partial MP4 retained.'
            elif message.type == Gst.MessageType.ERROR:
                error = message.parse_error()[0].message
            else:
                success = self.frames > 0
                if not success:
                    error = 'No video frames were captured.'
        finally:
            pipe.set_state(Gst.State.NULL)
            self.pipeline = self.source = self.audio_source = None
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
        if not success:
            raise RuntimeError(f'{error} File: {self.path}')
        return {'path': str(self.path), 'frames': self.frames,
                'duration': duration, 'audio': self.audio_enabled, 'quality': self.quality}
