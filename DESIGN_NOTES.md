# Lyra Control: studio workspace redesign

The main job is to frame a camera shot, adjust it and record it. This redesign keeps the existing GTK3 implementation and proven camera/recording paths, while replacing the layout and visual system.

## Research

Primary references inspected on 2026-11-01:

- [Elgato Camera Hub settings overview](https://help.elgato.com/hc/en-us/articles/4405055113357-Elgato-Facecam-Camera-Hub-Settings-Overview): separates zoom, picture, exposure and white balance. The useful principle is a task-oriented camera inspector; Lyra does not claim Facecam-only features.
- [GNOME boxed-list guidance](https://developer.gnome.org/hig/patterns/containers/boxed-lists.html): semantic groups, differentiated labels and values, symbolic icons, direct keyboard focus and bounded control widths. Applied as GTK3 layout principles, without introducing a GTK4/libadwaita dependency.
- [OBS quick-start guide](https://obsproject.com/kb/quick-start-guide): gives audio levels and recording controls clear, persistent locations. Lyra needs one camera, so it does not adopt OBS's multi-scene/dock complexity.

The local `design-ui-ux` catalog was consulted for studio dark styling and labelled control guidelines. Its web hero/CTA templates, gradients and purple palette were discarded because this is a working native camera tool.

## Direction

Compared a simple preferences window, an OBS-like dock system and a focused camera studio. Chosen: a large monitor canvas, fixed-width inspector and a full-width recording transport.

- Preview occupies the flexible space; the inspector stays 388 px wide. At 1360 × 840, the actual drawing area is 920 px wide. At 980 × 640 it remains 540 px wide.
- Capture quality, full-frame Portrait / Reels and Mirror remain directly under the monitor, independent of the selected tab.
- Camera contains the native zoom, an explicit secondary Reset action, expanded exposure controls and collapsible image adjustments. Disclosure choices survive refresh.
- Framing contains orientation, crop, effects and software zoom. Recording contains quality, microphone/level, destination and collapsed virtual-output options.
- Record/Stop, timer, selected microphone, quality and folder shortcut live in a bottom transport that stays visible across inspector tabs.
- Picture-only mode hides peripheral controls; an active recording retains Stop and its timer.
- A quiet status line retains the full message in its tooltip and selection text; errors receive a distinct text treatment. LIVE appears only after a preview frame arrives, and clears after failure/stop.

## Tokens

`ui_theme.py` is the single source of GTK color/font tokens.

- Background `#12171C`, panel `#1B232A`, surfaces `#25313A`.
- Accent `#E8BD72`, recording `#AB3344`, live state `#83CBA8`.
- Text `#E9EEF0`, secondary text `#ADBBC5`.
- IBM Plex Sans for controls; IBM Plex Mono for time, source mode and zoom readouts. Both are already installed; DejaVu is the fallback. No font downloads or remote assets.
- Standard symbolic GTK icons, visible focus rings and explicit menu/entry/list colors. Amber is for selection and starting preview; recording retains a red primary action. Once live, Stop preview is visually secondary.

## Verification

Rendered Camera, expanded Image, Framing and Recording at 1360 × 840; Recording at 1040 × 660; Camera at 980 × 640. Screenshots have the camera preview stopped. Also checked disabled, loading, connection error and live/recording transitions.

Interaction regressions cover capture controls outside the inspector, saved disclosure states, recording locks, compact error recovery and stale LIVE feedback. Existing native Auto/reset, codec, timing and lifecycle tests remain applicable. Live tests exercise the camera and selected microphones, remove temporary media and restore native test changes.

## Preview and connection recovery follow-up

The Camera inspector now owns its loading/error message and access/retry actions. Denied HID access after USB reconnection previously left an empty Camera page; successful reads now replace the recovery message with the real controls. Previously loaded values stay disabled while access is blocked.

The preview uses [GTK's frame-clock callback](https://docs.gtk.org/gtk3/method.Widget.add_tick_callback.html) rather than a fixed33ms poll. Measurements also isolated a half-rate Wayland shared-memory presentation path; this application prefers GTK3's GL compositor while preserving explicit environment overrides and GDK's existing context-failure fallback ([GTK3 source](https://github.com/GNOME/gtk/blob/gtk-3-24/gdk/gdkwindow.c)). A bounded three-sample display queue smooths USB/paint scheduling bursts, with up to two frames of buffering. The full-resolution recorder and virtual output remain independent.
