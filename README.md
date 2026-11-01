# Lyra Control

A Linux desktop workspace for the **Hollyland Lyra**: native camera controls, a processed video preview, MP4 recording with your choice of microphone, and virtual-camera output. Everything needed by the application is in this folder, including the bundled camview engine.

## Run

```sh
lyra-control
```

Or run directly from this folder:

```sh
/usr/bin/python3 app.py
```

Install or update the per-user launcher and desktop entry:

```sh
/usr/bin/python3 install.py
```

## Workspace

The English, left-to-right interface keeps a large preview beside three settings tabs. The Record/Stop button and elapsed time stay below the preview.

| Tab | Controls |
| --- | --- |
| **Camera** | Camera zoom, white balance, shutter, ISO, anti-flicker, brightness, contrast, saturation, sharpness and device-reported focus mode |
| **Framing** | Capture quality, orientation, full-frame portrait, frame shape, effects, mirror and software zoom |
| **Recording** | Microphone picker, input level while recording, destination folder and virtual-camera output |

Manual camera values use **Apply** and are independently read back. **Auto applies immediately when toggled**, with no extra Apply click. Auto values are periodically refreshed from the device. Read-only controls are disabled; **Refresh camera** reads all settings again.

### Reset image and exposure

Click **Reset to defaults** under **Image & exposure** to restore the original Lyra profile captured at first setup, including its Auto modes. Camera zoom, framing and recording preferences are unchanged. This is a verified image-settings restore, not an undocumented firmware/factory-reset command.

| Setting | Original profile |
| --- | --- |
| Anti-flicker | OFF |
| White balance | Auto; remembered manual value 5100 K |
| Shutter | Auto; remembered manual value 1/60 |
| ISO | Auto; remembered manual value 250 |
| Brightness / contrast / saturation | 0 |
| Sharpness | 50 |

The profile is preserved in `initial_camera_profile.json`, matched to the Lyra C4502 model and validated against current capabilities. The camera's `def` field is **not an immutable factory default**: live testing showed it changing with the last manual ISO value, so reset no longer trusts it. Anti-flicker is restored to OFF first to make shutter Auto and brightness available, then the original values and modes are applied and read back. List choices are matched by their labels rather than stale indices. If reset fails partway through, it attempts to restore the previous image settings and reports the result.

If you deliberately select 50/60 Hz anti-flicker, the camera can restrict shutter choices and remove Auto shutter support. The Auto checkbox stays visible but disabled in that state; turn anti-flicker OFF or reset the original profile to restore it.

### Portrait / Reels

Mount the camera vertically, then choose **Framing → Portrait / Reels · Full frame**. This rotates the entire image into portrait orientation without cutting a narrow strip from a landscape frame. Choose **90° counterclockwise** if the camera is mounted the other way. Orientation is remembered between launches.

**Portrait crop · 9:16** is a separate centered crop. Rotation happens before crop; horizontal mirror happens afterward. Camera zoom is the device's **1–4× digital zoom**. Software zoom affects the processed image; values below 1× add a black border.

### Record video and audio

1. Start the preview and set capture quality, orientation and appearance in **Framing**. New workspaces default to native **4K · 30 fps**, and your capture choice is remembered.
2. In **Recording**, choose **Best quality** (the default), **Smaller files**, or **Lossless · very large files**, then select your microphone, **System default microphone**, or **No audio · Video only**. Refresh the microphone list after connecting a device. Speaker-monitor sources are excluded.
3. Optionally choose a destination folder. The default is **`~/Videos/Lyra Control`**.
4. Click **Record** below the preview. The elapsed timer and microphone level show capture activity.
5. Click **Stop recording**. Wait for **Saved** before moving or opening the file.

Files use unique names such as `Lyra_2026-11-01_14-30-00_a1b2c3.mp4`. Existing files are never overwritten. Capture mode, recording quality, microphone and folder are remembered locally. Audio is captured only while recording.

Recordings use **H.264 video and AAC audio in MP4**, with the processed image's rotation, crop, effects, mirror and software zoom. Rounded window corners are a display treatment; the encoded video is rectangular. Full-resolution frames are fed directly from the native YUV video branch, independently of the GTK drawing rate. The GUI has a separate scaled display branch: resizing the window never reduces the recorded resolution. Neutral filters and the unused 1× software-zoom stage are bypassed to avoid unnecessary 4K processing. **Best quality** uses H.264 constant quality 16 with the superfast preset; **Smaller files** uses 21. **Lossless** uses quantizer 0 and preserves the processed 8-bit YUV420 pixels exactly; it cannot undo compression already performed inside the camera. Use Best quality for broad MP4 compatibility; lossless H.264 profiles are less widely supported. Encoding uses bounded buffering; under heavy CPU load frames can be dropped rather than freezing the preview. Resolution and requested FPS come from the selected capture mode; sustained performance depends on the computer.

Framing, microphone selection and preview stop are locked during a recording. Native camera controls can still be adjusted. Stop recording before changing capture settings. Closing the window finalizes an active recording before exiting. A capture/encoder error stops the recording and preserves the available file; short MP4 fragments improve recovery, but an interrupted file may be incomplete.

### Virtual camera for VLC, OBS and other apps

In **Recording**, click **Enable virtual camera**, then **Open output in VLC**, or select **Lyra Control** in another app. The device path is shown in the interface; it is currently `/dev/video42` on this computer but is discovered by identity rather than assumed.

Keep the preview running. Close the virtual-camera consumer before changing quality, orientation or frame dimensions, then reopen it afterward. Virtual output and MP4 recording can run together. Virtual output carries **video only**; choose the required microphone separately in the consuming app. Opening the physical Lyra directly bypasses the application's processing.

The first setup after a reboot may request system authorization to create a temporary `v4l2loopback` device and grant access to the current user. The helper does not install boot configuration or remove other applications' virtual outputs. If the module is already loaded without a Lyra Control device, it reports that condition and leaves those outputs intact.

### Window controls

**Picture only** hides the settings; **Show controls** or **Esc** restores them. An active recording keeps its Stop control visible. **F / F11** toggles fullscreen; F does not intercept typing in numeric fields. **Keep above** depends on the window manager.

## Requirements

The desktop application uses system Python 3, PyGObject/GTK 3, Cairo, GStreamer 1.20+ with GI bindings, and `v4l2-ctl`. Recording additionally needs `x264enc`, `h264parse`, `mp4mux`, `avenc_aac`, `aacparse`, `pulsesrc` and `level`; PulseAudio or PipeWire's PulseAudio service provides microphone selection through `pactl`. Virtual output needs `v4l2loopback`; permission helpers use `pkexec` and `setfacl`.

Typical Ubuntu packages:

```sh
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
  gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  gstreamer1.0-pulseaudio pulseaudio-utils v4l-utils acl policykit-1 \
  v4l2loopback-dkms
```

GTK/Cairo rendering works on native Wayland and X11; no external camview process, XWayland or `gtksink` is required.

If HID access is denied, click **Allow camera access**. The helper identifies the Lyra by USB identity and report descriptor, then grants temporary access without storing credentials. Permission may need to be granted again after reconnecting. If the physical camera is busy, close its direct capture in other apps and restart the preview.

## Project layout

```text
lyra-control/
├── app.py                    English GTK workspace
├── video_preview.py          Processed video and bounded frame delivery
├── recording.py              MP4 encoder and microphone discovery
├── virtual_camera.py         Processed video output to other apps
├── setup_virtual_camera.py   Temporary v4l2loopback setup
├── preferences.py            Local capture/quality/orientation/audio preferences
├── initial_camera_profile.json Original verified image defaults and Auto modes
├── lyra_backend.py           Native controls, defaults and readback
├── lyra_probe.py             Narrow HID protocol and device discovery
├── grant_lyra_access.py      Identity-based HID access helper
├── camview/                  Bundled engine and MIT license
├── assets/                   Application icon
├── tests/                    Unit, synthetic media and live integration checks
└── install.py                Per-user launcher installation
```

Preferences are stored in `~/.config/lyra-control/preview.json` (or `$XDG_CONFIG_HOME/lyra-control/preview.json`). No credentials or media are stored there. Firmware updates, AI framing and wireless-microphone pairing are outside the current implementation.

## Verification

Development dependencies: pytest and ffmpeg/ffprobe. Use a Python environment that can import the system GI bindings.

```sh
python3 -m pytest tests -q
```

The regression suite includes real synthetic H.264/AAC encoding and decoding, A/V timing, no-overwrite behavior, default dependency changes, protocol validation, geometry and effects. Tests with physical camera/microphone access are opt-in:

```sh
python3 tests/video_integration.py
python3 tests/portrait_integration.py
python3 tests/video_integration.py --portrait-output
GDK_BACKEND=x11 python3 tests/gui_smoke.py
GDK_BACKEND=x11 python3 tests/vlc_integration.py
python3 tests/recording_integration.py
python3 tests/auto_reset_integration.py
```

The recording integration test briefly captures the camera and each microphone into a temporary folder, checks streams/timing, and deletes the test media. Other video checks save only metadata; GUI screenshots are taken with the preview stopped. Native-control live checks restore the original values. Local validation metadata is under `artifacts/`.

The Auto/Reset integration check requires the original Auto profile at startup, exercises checkbox writes and recovery from changed manual/anti-flicker settings, then restores the pre-test image state. Lossless and quality regression tests use synthetic pixels; no user footage is retained.

## Source and license

The bundled camview engine is based on [JorgeGzm/camview](https://github.com/JorgeGzm/camview), with the original Jorge Guzman copyright and MIT terms preserved in `camview/LICENSE`. Integration changes are documented in `camview/INTEGRATION.md`.
