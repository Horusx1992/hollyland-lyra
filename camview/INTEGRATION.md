# Bundled camview

This directory contains the camview source used by Lyra Control, bundled from the local camview checkout at commit 1916cdd. Upstream: https://github.com/JorgeGzm/camview. Copyright and MIT terms are preserved in LICENSE.

Lyra Control imports this package from its own directory. It does not invoke an installed camview command or import source from the old project folder.

Integration change: PipelineBuilder accepts an appsink without assigning the video-overlay-only force-aspect-ratio property. video_preview.py consumes the frames in GTK and owns the pipeline lifecycle. camview's capture strategies, effects, cropping, mirror and software viewport zoom are reused directly.

The bundled PipelineBuilder also accepts validated 0/90/180/270 degree rotation before cropping. The final mirror remains independent and operates in the displayed orientation. Lyra Control optionally attaches a bounded tee branch to the named virtual camera; it never invokes the standalone camview application.

Lyra Control opts into neutral-effect bypass and omits the software viewport at 1× to avoid full-frame no-op processing. The default builder behavior stays compatible with the bundled standalone engine. The application uses a native I420 recording branch and a separate scaled RGB display branch; display resizing never reduces encoded dimensions.
