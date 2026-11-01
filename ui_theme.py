"""Studio UI tokens and native GTK3 styling; no remote fonts or web assets."""
COLORS = {
    'bg': '#12171C', 'panel': '#1B232A', 'surface': '#25313A',
    'hover': '#32424D', 'input': '#141C22', 'canvas': '#0B0E13',
    'line': '#36434D', 'border': '#687C89', 'text': '#E9EEF0',
    'muted': '#ADBBC5', 'disabled': '#91A0AA', 'accent': '#E8BD72',
    'accent_hover': '#F4CE8D', 'on_accent': '#151A1F', 'success': '#83CBA8',
    'danger': '#AB3344', 'danger_hover': '#B43A4B', 'danger_text': '#FFBBC5',
    'danger_border': '#EC9CA8',
}
SANS = 'IBM Plex Sans'
MONO = 'IBM Plex Mono'

STYLE = r'''
window {background: @bg; color: @text; font-family: "$SANS", "DejaVu Sans"; font-size: 13px;}
label {color: inherit;}
.title {font-size: 20px; font-weight: 600;}
.section {font-size: 14px; font-weight: 600;}
.eyebrow {font-size: 11px; font-weight: 600; letter-spacing: 1px; color: @muted;}
.muted {color: @muted; font-size: 12px;}
.mono {font-family: "$MONO", "DejaVu Sans Mono";}
.zoom-value {font-family: "$MONO", "DejaVu Sans Mono"; font-size: 26px; font-weight: 500; color: @text;}
.workspace-header {padding: 14px 18px; border-bottom: 1px solid @line;}
.source-chip, .badge {background: @surface; border: 1px solid @line; border-radius: 5px; padding: 5px 9px; font-size: 11px; color: @muted;}
.badge.live {color: @success;}
.badge.recording {color: @danger_text; border-color: @danger_border;}
.inspector {background: @panel; border: 1px solid @line; border-radius: 8px;}
.inspector-heading {padding: 14px 14px 8px;}
.card {background: @surface; border: 1px solid @line; border-radius: 7px; padding: 12px;}
.control-group {padding: 4px 0;}
.setting-row {padding: 4px 0;}
.setting-row button {min-height: 22px; padding: 3px 8px;}
.setting-row checkbutton {min-height: 20px;}
.zoom-panel.setting-row {padding: 12px;}
.canvas-shell {border: 1px solid @line; border-radius: 7px; background: @canvas;}
.placeholder {background: @canvas; color: @muted;}
.preview-heading {padding: 0 0 8px;}
.brand-icon {color: @accent;}
.capture-strip {padding: 8px 0 0;}
.transport {background: @panel; border-top: 1px solid @line; padding: 12px 18px;}
.record-status {color: @muted; font-size: 12px;}
.record-status.recording {color: @danger_text;}
.record-timer {font-family: "$MONO", "DejaVu Sans Mono"; font-size: 23px; color: @text;}
.status {color: @muted; font-size: 12px; padding: 6px 18px; background: @bg;}
.status.error {color: @danger_text;}
button {background: @surface; color: @text; border: 1px solid @border; border-radius: 5px; min-height: 28px; padding: 4px 11px; box-shadow: none; text-shadow: none; font-weight: 500;}
button:hover {background: @hover; border-color: @accent;}
button.primary {background: @accent; border-color: @accent; color: @on_accent;}
button.primary:hover {background: @accent_hover;}
button:focus {outline: 2px solid @accent; outline-offset: 2px;}
button:disabled {color: @disabled; background: @input; border-color: @line;}
button.flat {background: transparent; border-color: transparent;}
button.flat:hover {background: @surface; border-color: @line;}
button.icon-button {min-width: 28px; padding: 4px;}
button.record {min-height: 34px; min-width: 106px; background: @danger; border-color: @danger_border; color: @text; font-weight: 600; padding: 6px 18px;}
button.record:hover {background: @danger_hover;}
button.record:disabled {background: @surface; border-color: @line; color: @disabled;}
spinbutton, combobox {min-height: 30px;}
spinbutton, entry {background: @input; color: @text; border-color: @border; border-radius: 5px;}
spinbutton entry {background: @input; color: @text; border: none;}
spinbutton:disabled, entry:disabled {background: @input; color: @disabled; border-color: @line;}
spinbutton button {border-color: @line; min-width: 20px; padding: 2px 6px;}
combobox button, combobox cellview {color: @text;}
combobox button:disabled, combobox:disabled cellview {color: @disabled;}
menu, popover {background: @panel; color: @text; border: 1px solid @border;}
menu menuitem {background: @panel; color: @text; min-height: 28px; padding: 4px 12px;}
menu menuitem:hover, menu menuitem:selected {background: @accent; color: @on_accent;}
menu menuitem:disabled {background: @panel; color: @disabled;}
menu menuitem cellview, menu menuitem label {color: inherit;}
.view {background: @input; color: @text;}
.view:selected {background: @accent; color: @on_accent;}
headerbar {background: @panel; color: @text; border-color: @line;}
checkbutton {color: @text; min-height: 28px;}
checkbutton check {background: @input; border: 1px solid @border; border-radius: 3px; min-width: 14px; min-height: 14px;}
checkbutton check:checked {background: @accent; color: @on_accent; border-color: @accent;}
checkbutton:disabled {color: @disabled;}
scale trough {background: @input; min-height: 4px; border: 1px solid @line;}
scale highlight {background: @accent;}
scale slider {background: @accent; border: 1px solid @accent_hover; min-width: 14px; min-height: 14px;}
scale value {color: @muted; font-family: "$MONO", "DejaVu Sans Mono"; font-size: 12px;}
separator {background: @line; min-height: 1px;}
notebook, notebook stack, notebook header {background: @panel; color: @text; border: none;}
notebook header {border-bottom: 1px solid @line;}
notebook header tab {background: transparent; color: @muted; padding: 8px 12px; border: none; border-bottom: 2px solid transparent;}
notebook header tab:checked {color: @accent; border-bottom-color: @accent;}
notebook header tab:hover {background: @surface;}
expander {color: @text;}
expander title {font-weight: 600; min-height: 30px;}
progressbar trough {background: @input; border: 1px solid @border; min-height: 6px; border-radius: 3px;}
progressbar progress {background: @success; min-height: 6px; border-radius: 3px;}
progressbar text {color: @muted; font-size: 11px;}
scrolledwindow {border: none;}
scrollbar {background: transparent;}
scrollbar slider {background: @border; border-radius: 4px; min-width: 5px; min-height: 24px;}
'''
CSS = ('\n'.join(f'@define-color {name} {value};' for name, value in COLORS.items())
       + '\n' + STYLE.replace('$SANS', SANS).replace('$MONO', MONO)).encode()
