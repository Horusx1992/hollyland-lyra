# Implementation contract

## Preview cadence and missing Camera controls — 2026-11-01

- Outcome: smooth 1080p60 preview and visible/recoverable camera-control state.
- Acceptance: remove the approximately30fps display ceiling; show settings after access restoration and actionable access/retry state on failure.
- Invariants: native-resolution MP4/virtual output and camera values remain unchanged; bounded rendering, release callbacks on stop, preserve user preferences and delete temporary media.
- Scope/order: reproduce synthetic/physical cadence and denied HID access → frame-clock rendering/GL/bounded jitter buffer → Camera-tab recovery → live A/V, GTK and regression verification.
- Evidence: opt-in tests/preview_performance.py stores metadata only; tests cover USB bursts, bounded hidden buffering, actual asynchronous permission failure/retry and original controls.

## Researched studio GUI redesign — 2026-11-01

- Outcome: a clearer native English camera workspace, informed by camera-software and GNOME interaction research.
- Acceptance: large preview, bounded inspector, always-visible capture shortcuts and recording transport; fewer repeated hints/oversized control groups; readable focus/contrast across system themes and compact sizes.
- Invariants: retain verified HID/Auto/reset, native-resolution recording, microphone selection and virtual output; capture settings locked while recording; no permanent native-setting changes or saved test footage.
- Scope/order: inspect Camera Hub/OBS/GNOME and local design catalog → define studio tokens/layout → native widgets and state feedback → rendered/interaction/recording checks → README/design notes.
- Evidence: real GTK captures at1360x840,1040x660,980x640; popup/theme contrast; input/feedback/disclosure tests; existing live camera and A/V integration checks.

## Original defaults, immediate Auto and MP4 quality repair — 2026-11-01

- Outcome: restore first-setup image values now; fix Reset and Auto; record native high-resolution detail without degrading frame delivery.
- Acceptance: one-click Auto writes/reads back immediately; Reset restores the first verified values and Auto modes; new workspace defaults to4K30, remembers capture/encoding quality, preserves native dimensions in MP4.
- Invariants: reset excludes zoom and rolls back partial failures; no dependence on mutable firmware def; recording stays bounded and finalizes A/V on stop/close; no persistent test media.
- Scope/order: restore/reproduce → baseline profile and Auto handler → capture/codec quality and stream timing → optimize measured4K bottlenecks → real and synthetic regression checks/docs.
- Checks: actual HID modes/defaults; GTK no-Apply regression; decoded pixel/PSNR comparison and exact processed-pixel lossless case; native4K MP4 packet rate/sync/full decode; repeated microphone recording and lifecycle checks.

## English workspace, image defaults and audiovisual recording — 2026-11-01

- Outcome: English GUI/README, explicit image/exposure defaults reset, microphone-selectable video/audio recording, clearer native GTK layout.
- Acceptance: Camera/Framing/Recording tabs beside a large preview; persistent record/stop/timer; MP4 contains processed portrait/mirror/effects video and selected microphone; EOS finalizes playable files, including close/error paths.
- Invariants: zoom and unsupported controls excluded from image reset; defaults come from device metadata, existing Auto modes retained where the refreshed camera capabilities permit them; no overwritten recordings; bounded video buffering and responsive UI; native/virtual preview survives recording stop.
- Order: verified device defaults/audio/encoders → reset backend and recorder → English tabbed GUI → README and integration/regression evidence.
- Checks: reset prevalidation/partial failures; synthetic A/V recording analyzed/decoded with ffprobe/ffmpeg; physical microphones and portrait camera capture; start/stop/repeat/close/error cases; GTK layout and keyboard focus.

## Portrait orientation and external output — 2026-11-01

- Outcome: correct physically rotated Lyra video in the unified preview and VLC.
- Acceptance: 0/90/180/270 degree rotation before crop, independent horizontal mirror, full portrait frames; optional named virtual-camera output carrying the same processed video.
- Invariants: preserve native camera settings, avoid touching physical/unrelated output nodes, bounded preview/output buffering, release pipeline on stop/close; no firmware writes.
- Scope/order: verify supplied quick guides and V4L2 modes; implement rotation geometry/pipeline, virtual output and identity-based setup, GTK controls, tests/docs.
- Checks: asymmetric synthetic frames for rotation/mirror order and dimensions; live portrait preview plus independent V4L2 consumer; pipeline lifecycle/error checks and relevant regression suite. Never save live camera frames.

## Unified application contract — 2026-11-01

- Outcome: integrate camview and native Lyra controls in one local application/folder.
- Acceptance: embedded video in the control window; no external camview invocation or source dependency; preserved capture modes, filters/mirror/shapes/software zoom, preview-only/fullscreen, native setting readback.
- Invariants: preserve native protocol bounds/permissions, release pipeline on stop/error/close, bound frame buffering, preserve upstream license, keep existing project checkout intact.
- Implementation order: bundle camview source → embedded appsink/GTK view → integrate controls/lifecycle → regression and live tests → update launcher/docs.
- Evidence: 128 regression tests; embedded live frames at 720p30, 1080p30/60 and 4K30; GTK/native-control and video-lifecycle checks. Test environment PATH excludes the installed camview command.

- Outcome: a local GTK3 camera control application, using the verified Lyra HID protocol.
- Acceptance: discover camera, read its settings, apply zoom and enabled image controls with readback, open/close an owned camview preview, recover from denied access/disconnection.
- Invariants: never touch another HID device, never send upgrade/arbitrary commands, serialize camera operations, do not block GTK, retain user changes on refresh, restore all live test changes.
- Scope: native zoom/image controls; unsupported controls remain disabled; preview reuses the installed camview. No firmware updates, recording or virtual camera.
- Verification: protocol/backend tests, meaningful permission/readback/error cases, GTK render and interaction checks, reversible live-camera tests.

Design: Arabic GTK interface, dark graphite surfaces, blue actions, readable system Arabic font, explicit Apply per setting. No remote assets. Research evidence remains in /home/horusx/.cache/lyra-research/FINDINGS.md.

## Verified 2026-11-01

- New standalone source in /home/horusx/projects/lyra-control; existing camview source unchanged.
- Native camera snapshot reads ten displayed settings, with focus mode disabled by capability and nine enabled writers.
- All nine writers checked by reversible changes and independent readback; original values/modes restored. Camera state/proof in live-validation.json and artifacts/image-controls-validation.json.
- 11 offline protocol/backend tests pass. Python compilation and ruff F/E9 pass.
- Live GTK smoke passes: ten rows, zoom Apply/restore through widget callback, owned camview preview alive, simulated permission error and live reconnect recovery. Screenshot artifacts/interface.png was visually inspected under XWayland. Default GTK Wayland startup/data read also completed; screenshot capture there returned black, so only XWayland capture is visual evidence.
- Main text contrast pairs measured 5.92:1 or greater, Arabic RTL alignment and mixed numeric directions inspected.
- Per-user launcher and desktop entry installed by install.py, no system-wide installation.
- Privileged helper runs Python with -B in GUI to avoid creating root-owned bytecode cache in user source. It grants only the discovered and descriptor-validated Lyra node.
- UI serializes HID operations in one background worker; refresh and apply remain responsive. Preview discovery is also performed off the GTK thread. Permission authentication is cancellable on window close.

Remaining optional work: embedded video preview, autofocus/AI/audio controls, recording/virtual camera, persistent device permissions. No firmware writes implemented.

## Unified delivery verified

- camview source and MIT license bundled under camview/; all runtime imports resolve inside this project. Installed camview command absent from PATH during integration tests.
- PipelineBuilder adapted to appsink without overlay-only properties; RGB frames held in a bounded single-buffer queue and drawn in GTK. No external preview process or X11 window handles.
- 128 pytest regressions passed, including synthetic RGB video pipeline and original camview geometry/effect/pipeline coverage. ruff F/E9 clean.
- Live video modes verified:720p30,1080p30,1080p60,4K30. Captured only frame counts/sizes, not user camera images.
- Native Wayland (GdkWaylandDisplay) integration produced5received/5drawn frames at720p without XWayland.
- GTK live test verified native zoom apply/restore while video runs, phone shape, mirror, grayscale effect, software zoom black padding, preview-only mode, fullscreen, permission error/recovery. Stop/close set pipelines NULL.
- Fullscreen and preview-only share the existing window; preview-only lowers minimum size and restores the previous layout/size.
- Updated per-user launcher/desktop entry and README; original camview checkout unchanged.

## Dropdown readability and zoom capability — 2026-11-01

- Reproduced white popup text on the system theme's near-white menu background: measured contrast 1.00:1.
- Explicitly style GTK popup menus and combo text, including highlighted and disabled entries. Checked all seven dropdowns across the current theme and Adwaita light/dark: 21 combinations, minimum contrast 5.92:1. Inspected quality and ISO popup screenshots; no camera images captured.
- Ruff F/E9 and Python compilation passed. Manual GTK validation results are in artifacts/dropdown-validation.json.
- Read the connected camera again, without changing settings: native zoom cmd566 reports min1/max4/step0.1/current1. Command569 reports mode2, not an additional zoom factor. No device-supported 0.5x/0.25x native options were exposed. Responses preserved in artifacts/zoom-capability.json and artifacts/zoom-mode-capability.json.

## Portrait delivery verified — 2026-11-01

- Read both supplied local quick guides in full and visually inspected relevant EN-5/EN-6/EN-10 pages. They cover mounting, auto-framing, privacy, digital zoom1–4x and (combo) LARK A1 pairing, but do not document an automatic portrait correction control. V4L2 advertises only landscape dimensions and no usable rotation control; no undocumented native writes attempted.
- Added validated rotation before crop, preserving full portrait frame dimensions, with independent horizontal mirror afterward. Orientation is remembered in ~/.config/lyra-control/preview.json. Native camera settings remain unchanged by orientation.
- Added temporary named v4l2loopback output. Existing module was available; helper created /dev/video42 with exclusive capture/output caps and user ACL. No persistent module configuration, firmware changes, or removal of unrelated virtual outputs.
- Shared processed pipeline feeds bounded preview and virtual output branches. Output dimensions must be changed with the external consumer closed, then reopened; UI/docs explain this. Rounded window edges are display-only, video output remains rectangular; audio is not exported.
- 145 pytest regressions passed, including actual asymmetric synthetic pixel rotation/mirror checks, crop/viewport sizing, orientation preferences and rejection of physical devices as output. Ruff F/E9 passed.
- Native Wayland live virtual output passed four modes:720x1280,1080x1920@requested30/60,2160x3840. This checks frame delivery/negotiation, not sustained FPS performance.
- Independent GStreamer V4L2 consumer received1080x1920 at90/270 degrees,1080x1080 circle crop and1920x1080 restored landscape; old pipelines released to NULL.
- GTK output buttons and VLC rawvideo decoder validated at1080x1920. VLC logged 'Received first picture' and exited normally via its own quit command. GUI native zoom apply/restore and existing shapes/filter/mirror/permission/fullscreen smoke also passed. Live camera frames were never saved; screenshot has preview stopped.
- Evidence: artifacts/portrait-validation.json, portrait-modes.json, vlc-validation.json and portrait-interface.png. Reproduction scripts: tests/portrait_integration.py, tests/video_integration.py --portrait-output and tests/vlc_integration.py.

## English workspace and recording delivery verified — 2026-11-01

- Replaced the RTL controls wall with an English LTR workspace: large preview, Camera/Framing/Recording tabs, persistent Record/Stop and elapsed timer. Camera settings remain applied/read back independently; framing and audio selection lock while recording. Numeric typing no longer triggers the F fullscreen shortcut.
- English labels, error messages, desktop entry and README. Preserved dark graphite/blue palette with system Noto Sans/DejaVu Sans; red highlights active recording, disabled controls remain distinct. Fixed GTK progress text colors explicitly, retaining popup contrast fixes.
- Added a narrowly scoped image/exposure reset. Live testing revealed that anti-flicker60Hz changes shutter list indices, removes shutter Auto and disables brightness. Reset now applies anti-flicker first, re-reads every subsequent default/capability, skips unavailable controls, reports mode changes and rebuilds all rows. No camera zoom/reset-firmware command. GUI/live checks restored the user's original values in dependency order.
- New recording.py owns a separate bounded MP4 pipeline, H.264 x264 ultrafast/quality21 + optional AAC192k/stereo48k. Samples arrive from the camera streaming thread, independently of the GTK draw rate, and use the recording pipeline's clock for A/V timing. MP4 fragments are1s; Stop sends EOS to both tracks and waits asynchronously for mux finalization. Exclusive file descriptors prevent overwrite; encoder queues and threads are bounded.
- Microphone list uses PulseAudio/PipeWire device IDs and excludes speaker monitors. Users can select a physical input, system default, or no audio; meter runs only during recording. Orientation, microphone and destination are stored atomically in the existing local preferences file. Default media folder is ~/Videos/Lyra Control.
- Native Wayland live recording used both built-in and Lyra microphones, video-only, and closing the window mid-recording, with virtual output enabled. ffprobe verified1080x1920 H.264/AAC tracks, durations/start offsets; ffmpeg fully decoded each file. Repeated successful runs produced approximately79–88 video packets per1.4s at requested1080p60. This is a short functional check, not a sustained performance guarantee. Test media were deleted.
- Existing preview/portrait output was rechecked across720p30,1080p30/60,4K30 after the streaming-thread change. VLC received its first decoded portrait frame. Original native zoom apply/restore and GUI lifecycle checks passed.
- 157 pytest regressions pass, including synthetic real-codec recording/decoding/sync, repeated sessions, no overwrite, stream-error cleanup and first-cause retention, dependency-aware defaults, and preference preservation. Ruff F/E9 and compilation passed.
- Visually inspected all three tabs at1280x820 and compact1040x660, with preview stopped for screenshots. A text walk found no Arabic GUI labels. Evidence: artifacts/english-*.png, english-layout.json, defaults-validation.json, defaults-gui-validation.json, recording-validation.json; live A/V script tests/recording_integration.py. Refreshed the installed desktop entry.

## Original-profile / Auto / MP4 repair delivered — 2026-11-01

- Restored the earliest verified readings from the research ledger: Anti-flickerOFF; WB5100/shutter1/60/ISO250 with Auto enabled; brightness/contrast/saturation0; sharpness50; zoom1. Unsupported focus mode remains unchanged.
- Two red reproductions established the main control bugs: toggling the actual GTK Auto checkbox made zero backend calls; manually changing ISO250→320 changed firmware def4→5. Thus the previously implemented camera-def reset was not restoring immutable factory defaults. No firmware factory-reset opcode is claimed.
- Added initial_camera_profile.json from the original evidence, validated against Lyra C4502 and current ranges/list labels. Reset applies dependency order, restores remembered manual baselines plus original Auto modes, refreshes controls, and attempts rollback if a write fails. Zoom excluded. Mutable def is no longer used as a factory-default source.
- Auto writes and reads back immediately; UI state reverts on busy/error instead of displaying an unsent toggle. Programmatic updates suppress toggle callbacks. Conditional Auto controls stay visible/disabled when firmware restrictions apply; an asynchronous poll updates device-reported Auto values without overwriting pending changes.
- A third red reproduction showed new workspaces silently selecting720p. Capture mode now defaults to native4K30 and is remembered, along with encoder quality. Best quality usesCRF16/superfast; smaller files uses21; lossless usesQP0 for processed8-bit I420 pixels. Synthetic decode measured42.81dB vs38.21dB luma PSNR on the same texture, and lossless decoded bit-exactly. These synthetic scores are not a camera scene quality guarantee.
- Measured the4K path before optimization: native MJPG and decoded RGB~30fps, processed normal path~22fps, MP4~16fps. Removed neutral filters and the unused1x viewport, kept native I420 through recording, and gave GTK a separate scaled RGB branch. Source/MP4 dimensions are unchanged by window resizing. Short native4K portrait tests then produced60–65 packets in~2.1–2.2s with synchronized audio, full ffmpeg decode passed; no sustained-FPS guarantee is implied.
- Repeated real recording exposed an existing intermittent mux error, 'Buffer has no PTS'. Recorder now uses an explicit shared system clock/base and strictly increasing video PTS/DTS before appsrc, rather than relying on asynchronous automatic timestamps during audio startup. Added a deterministic pre-appsrc timestamp regression. Two repeated microphone/video-only/close test runs passed afterward.
- Live Auto UI test verified Manual↔Auto for WB/shutter/ISO without Apply, then recovered the original profile after manual WB6000/ISO1600 and60Hz changes. Existing GUI zoom/effects/shape/lifecycle, independent virtual consumer and VLC portrait decoding passed. Updated saved capture to4K30 and quality toBest for handoff; test scripts preserve user preferences.
- 162 pytest regressions passed, plus Ruff F/E9 and compilation. Updated English README and inspected all three English tabs at1280x820 and1040x660 with camera images excluded from screenshots.
- Evidence: artifacts/default-field-repro.json, restored-first-setup.json, auto-reset-repair.json,4k-stage-rate.json,4k-recording-repair.json and recording-validation.json. Live clips were temporary and deleted. Regression entry points include tests/test_auto_ui.py, test_capture_defaults_ui.py, test_recording_quality.py, tests/auto_reset_integration.py and tests/recording_integration.py.

## Studio redesign delivered — 2026-11-01

- Researched primary Camera Hub/OBS documentation and GNOME HIG; consulted the local design-ui-ux catalog. Selected a focused native studio rather than a generic web/dock layout. References and tradeoffs are in DESIGN_NOTES.md.
- Added ui_theme.py with named charcoal/amber/red/green GTK tokens and installed IBM Plex Sans/Mono with DejaVu fallbacks. No remote assets, framework migration or camera/encoding changes.
- Replaced the controls-wall layout with a920px preview at1360px window width, a388px bounded inspector, visible capture/portrait/mirror strip, compact disclosures and full-width recording transport. Fixed inherited expansion that had left unused space between panes. At980px width the drawing area remains540px wide.
- Secondary hints are concentrated by task rather than repeated per row. Image and virtual-camera controls use disclosure; refresh preserves disclosure state. Manual Apply is disabled while Auto is enabled; Auto's immediate verified write path is unchanged.
- Added true stopped/live feedback and a stopped-preview action, compact full-message status/tooltips, symbolic accessible controls, contextual primary preview action and folder/record-settings shortcuts. Picture-only mode keeps only Stop/timer when recording, and failure cannot leave a stale LIVE badge.
- Rendered all three tabs, image disclosure,1040x660 and980x640 layouts using actual device settings with preview stopped. Inspected screenshots. Tested21 dropdown/theme combinations; minimum popup contrast5.92:1. Text/button palette pairs are at least4.92:1, including Record hover.
- Camera was initially disconnected; user reconnected it. Re-granted temporary ACL to the identity/descriptor-verified Lyra hidraw node, then completed live GUI zoom apply/restore, shapes/filters/permission/fullscreen tests. Native recording passed both physical microphones, video-only, virtual output and close/finalization; temporary clips were deleted and user capture/quality preferences restored.
-167 pytest regressions passed, including five new studio interaction regressions. Ruff F/E9 and compilation passed. Existing GLib deprecation and repeated-application-name test warnings are unchanged behavior and do not affect execution.
- Evidence: artifacts/studio-*.png, studio-layout.json, studio-contrast.json, studio-popup-contrast.json and recording-validation.json. Native camera settings and user media preferences were preserved. Updated README navigation and added opt-in tests/ui_layout.py and tests/ui_contrast.py.

## Preview cadence and Camera recovery delivered — 2026-11-01

- Reproduced 1080p60 synthetic capture at59.86fps with preview29.93fps. Physical capture showed the same approximately30fps limit. The fixed33ms GUI timer was one cause; frame-clock timing alone still exposed a separate half-rate GTK3 Wayland shared-memory path. Enabling GDK's GL compositor resolved that path; environment overrides are preserved, and GTK's context-failure fallback remains available.
- Latest-only display buffering also discarded burst-delivered frames when USB and paint phases crossed. Replaced it with an explicitly bounded three-sample FIFO, initially waiting for two samples. This adds up to two frames of display buffering; native recording/output remain independent. GTK's frame clock handles presentation; a separate100ms bus watch still detects EOS/errors while the window is hidden. Both callbacks and retained samples are released on stop.
- Physical Wayland preview measured59.65fps after the changes; subsequent short measurements with the full workspace measured53.53fps. These are local short-run measurements, not a sustained60fps guarantee. Native input and display conversion remained approximately60fps. Metadata only in artifacts/preview-pacing-GdkWaylandDisplay-Lyra.json and workspace-preview-pacing.json; no camera images retained.
- Missing Camera controls reproduced as PermissionError on the reconnected identity/descriptor-verified Lyra HID interface. Restored temporary access using the existing helper. Camera now contains explicit loading/access/retry states; verified successful reads replace them with all ten native rows. Stale rows remain disabled on failure. Actual asynchronous denied-refresh/retry callbacks are covered, not only a mock layout.
- Full regression suite172 passed; after adding a hidden-window EOS regression and final recovery-message adjustment,11 focused tests passed. Ruff F/E9 and compilation clean. Real camera/microphone/video-only/portrait/virtual-output recording checks passed again after the final display-buffer change, including MP4 full decode, A/V timing and close finalization. Temporary media deleted and user1080p60/lossless/microphone/rotation preferences preserved.
- Inspected actual read-only GTK Camera and recovery screenshots at1360x840 and980x640; the existing layout checks passed for all tabs and compact sizes. Updated README and DESIGN_NOTES with the measured behavior and GTK primary references. Left the actual English workspace open, on1080p60 with all ten Camera controls loaded.
