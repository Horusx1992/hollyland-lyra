"""Construção do pipeline GStreamer.

Padrões aplicados:
- Strategy: cada formato de câmera (MJPEG, YUYV, NV12) sabe montar seus próprios
  caps e cadeia de decodificação; adicionar um formato novo não altera o
  builder.
- Builder: monta o pipeline passo a passo e valida antes de produzir o
  resultado final.

Segurança: o pipeline é montado elemento a elemento com ``ElementFactory`` e
os valores entram como *propriedades* (``set_property``), nunca como sintaxe.
Isso torna impossível injetar elementos através de um valor — ao contrário de
``Gst.parse_launch()``, que interpreta a string como uma descrição completa de
pipeline. ``build_description()`` continua existindo apenas para depuração e
testes; nada a executa.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from camview.config import CaptureConfig, PixelFormat
from camview.effects import NORMAL, Effect
from camview.geometry import NO_CROP, crop_borders, zoomed_content

FLIP_ELEMENT = "flip"
ROTATE_ELEMENT = "rotate"
CROP_ELEMENT = "crop"
SINK_ELEMENT = "sink"
FILTER_ELEMENT = "capsfilter"
BALANCE_ELEMENT = "balance"
GAMMA_ELEMENT = "gamma"
COLOR_ELEMENT = "color"
FUN_ELEMENT = "fun"
ZOOM_SIZE_ELEMENT = "zoom_size"
ZOOM_BOX_ELEMENT = "zoom_box"


class PipelineError(RuntimeError):
    """Falha ao montar o pipeline (elemento ausente ou não encadeável)."""


_color_effects: bool | None = None


def color_effects_available() -> bool:
    """True se o elemento coloreffects (gst-plugins-bad) está disponível.

    Sem ele os filtros que usam preset de cor (sepia, xpro, ...) ainda
    funcionam, mas só com a parte de contraste/saturação/gama.
    """
    global _color_effects
    if _color_effects is None:
        try:
            from gi.repository import Gst

            _color_effects = Gst.ElementFactory.find("coloreffects") is not None
        except (ImportError, ValueError):
            _color_effects = False
    return _color_effects


_video_crop: bool | None = None


def crop_available() -> bool:
    """True se o elemento videocrop (gst-plugins-good) está disponível.

    Sem ele o contorno ``phone`` ainda recorta a *janela*, mas a imagem
    aparece deitada dentro dela, com tarjas pretas.
    """
    global _video_crop
    if _video_crop is None:
        try:
            from gi.repository import Gst

            _video_crop = Gst.ElementFactory.find("videocrop") is not None
        except (ImportError, ValueError):
            _video_crop = False
    return _video_crop


def apply_crop(pipeline, borders: tuple[int, int, int, int]) -> None:
    """Muda o recorte do pipeline em execução (troca de contorno ao vivo)."""
    crop = pipeline.get_by_name(CROP_ELEMENT)
    if crop is None:
        return
    for name, value in zip(("left", "right", "top", "bottom"), borders, strict=True):
        crop.set_property(name, value)


_digital_zoom: bool | None = None


def digital_zoom_available() -> bool:
    """Verifica os elementos de recorte, escala e bordas do zoom digital."""
    global _digital_zoom
    if _digital_zoom is None:
        try:
            from gi.repository import Gst

            _digital_zoom = all(
                Gst.ElementFactory.find(name) is not None
                for name in ("videocrop", "videoscale", "videobox")
            )
        except (ImportError, ValueError):
            _digital_zoom = False
    return _digital_zoom


def _viewport_layout(width: int, height: int, zoom: float):
    content = zoomed_content(width, height, zoom)
    borders = tuple(-value for value in crop_borders(width, height, content))
    caps = (
        f"video/x-raw,width={content.width},height={content.height},pixel-aspect-ratio=1/1"
    )
    return caps, borders


def apply_viewport(pipeline, width: int, height: int, zoom: float) -> None:
    """Mantém o tamanho de saída e centraliza a imagem reduzida ao vivo."""
    from gi.repository import Gst

    size = pipeline.get_by_name(ZOOM_SIZE_ELEMENT)
    box = pipeline.get_by_name(ZOOM_BOX_ELEMENT)
    if size is None or box is None:
        return
    caps, borders = _viewport_layout(width, height, zoom)
    size.set_property("caps", Gst.Caps.from_string(caps))
    for name, value in zip(("left", "right", "top", "bottom"), borders, strict=True):
        box.set_property(name, value)


def apply_effect(pipeline, effect: Effect) -> None:
    """Aplica os parâmetros de cor de um efeito ao pipeline em execução.

    Só funciona entre efeitos que usam o mesmo elemento extra (``element``);
    trocar o elemento exige reconstruir o pipeline.
    """
    balance = pipeline.get_by_name(BALANCE_ELEMENT)
    if balance is not None:
        balance.set_property("contrast", effect.contrast)
        balance.set_property("brightness", effect.brightness)
        balance.set_property("saturation", effect.saturation)
        balance.set_property("hue", effect.hue)
    gamma = pipeline.get_by_name(GAMMA_ELEMENT)
    if gamma is not None:
        gamma.set_property("gamma", effect.gamma)
    color = pipeline.get_by_name(COLOR_ELEMENT)
    if color is not None:
        color.set_property("preset", effect.preset)


class FormatStrategy(ABC):
    """Como capturar e decodificar um formato específico da câmera."""

    @abstractmethod
    def source_caps(self, capture: CaptureConfig) -> str:
        """Caps negociados com o v4l2src."""

    @abstractmethod
    def decode_chain(self) -> list[str]:
        """Elementos necessários para converter o formato em vídeo cru."""


class MjpegStrategy(FormatStrategy):
    def source_caps(self, capture: CaptureConfig) -> str:
        return (
            f"image/jpeg,width={capture.width},height={capture.height},"
            f"framerate={capture.fps}/1"
        )

    def decode_chain(self) -> list[str]:
        return ["jpegdec"]


class YuyvStrategy(FormatStrategy):
    def source_caps(self, capture: CaptureConfig) -> str:
        return (
            f"video/x-raw,format=YUY2,width={capture.width},height={capture.height},"
            f"framerate={capture.fps}/1"
        )

    def decode_chain(self) -> list[str]:
        return []


class Nv12Strategy(FormatStrategy):
    def source_caps(self, capture: CaptureConfig) -> str:
        return (
            f"video/x-raw,format=NV12,width={capture.width},height={capture.height},"
            f"framerate={capture.fps}/1"
        )

    def decode_chain(self) -> list[str]:
        return []


_STRATEGIES: dict[PixelFormat, FormatStrategy] = {
    PixelFormat.MJPG: MjpegStrategy(),
    PixelFormat.YUYV: YuyvStrategy(),
    PixelFormat.NV12: Nv12Strategy(),
}


def strategy_for(pixel_format: PixelFormat) -> FormatStrategy:
    try:
        return _STRATEGIES[pixel_format]
    except KeyError as exc:
        raise ValueError(f"no strategy registered for format: {pixel_format}") from exc


class PipelineBuilder:
    """Monta o pipeline de exibição a partir de uma configuração validada."""

    def __init__(self) -> None:
        self._capture: CaptureConfig | None = None
        self._mirror = False
        self._rotation = 0
        self._sink = "xvimagesink"
        self._effect: Effect = NORMAL
        self._optimize_neutral = False
        self._crop: tuple[int, int, int, int] = NO_CROP
        self._viewport: tuple[int, int, float] | None = None

    def with_capture(self, capture: CaptureConfig) -> PipelineBuilder:
        self._capture = capture
        return self

    def with_mirror(self, mirror: bool) -> PipelineBuilder:
        self._mirror = mirror
        return self

    def with_rotation(self, degrees: int) -> PipelineBuilder:
        if degrees not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180 or 270 degrees")
        self._rotation = degrees
        return self

    def with_effect(self, effect: Effect, optimize_neutral: bool = False) -> PipelineBuilder:
        self._effect = effect
        self._optimize_neutral = optimize_neutral
        return self

    def with_crop(self, borders: tuple[int, int, int, int]) -> PipelineBuilder:
        """Pixels a descartar de cada lado (esquerda, direita, topo, base)."""
        if any(border < 0 for border in borders):
            raise ValueError(f"invalid crop borders: {borders}")
        self._crop = tuple(borders)
        return self

    def with_sink(self, sink: str) -> PipelineBuilder:
        self._sink = sink
        return self

    def with_viewport(self, width: int, height: int, zoom: float) -> PipelineBuilder:
        zoomed_content(width, height, zoom)
        self._viewport = (width, height, zoom)
        return self

    def _validated_capture(self) -> CaptureConfig:
        if self._capture is None:
            raise ValueError("capture configuration not set (with_capture)")
        return self._capture

    def build_description(self) -> str:
        """Descrição legível do pipeline, para logs e testes.

        NÃO é executada: o pipeline real é montado por ``build()`` via
        ElementFactory. Serve para inspecionar o que será construído.
        """
        capture = self._validated_capture()
        strategy = strategy_for(capture.pixel_format)
        flip_method = "horizontal-flip" if self._mirror else "none"
        effect = self._effect
        elements = [
            f"v4l2src device={capture.device}",
            strategy.source_caps(capture),
            *strategy.decode_chain(),
        ]
        if self._rotation:
            method = {90: "clockwise", 180: "rotate-180", 270: "counterclockwise"}[self._rotation]
            elements.append(f"videoflip name={ROTATE_ELEMENT} method={method}")
        if crop_available():
            left, right, top, bottom = self._crop
            elements.append(
                f"videocrop name={CROP_ELEMENT} left={left} right={right} "
                f"top={top} bottom={bottom}"
            )
        elements.append("videoconvert")
        if not (self._optimize_neutral and effect == NORMAL):
            elements += [
                f"videobalance name={BALANCE_ELEMENT} contrast={effect.contrast} "
                f"brightness={effect.brightness} saturation={effect.saturation} hue={effect.hue}",
                f"gamma name={GAMMA_ELEMENT} gamma={effect.gamma}",
            ]
        if color_effects_available() and not (self._optimize_neutral and effect == NORMAL):
            elements += [
                "videoconvert",
                f"coloreffects name={COLOR_ELEMENT} preset={effect.preset}",
            ]
        if effect.element:
            elements += ["videoconvert", f"{effect.element} name={FUN_ELEMENT}"]
        elements.append("videoconvert")
        if self._viewport is not None and digital_zoom_available():
            caps, borders = _viewport_layout(*self._viewport)
            left, right, top, bottom = borders
            elements += [
                "videoscale",
                f"capsfilter name={ZOOM_SIZE_ELEMENT} caps=\"{caps}\"",
                f"videobox name={ZOOM_BOX_ELEMENT} fill=black "
                f"left={left} right={right} top={top} bottom={bottom}",
            ]
        elements += [
            f"videoflip name={FLIP_ELEMENT} method={flip_method}",
            f"{self._sink} name={SINK_ELEMENT}"
            + ("" if self._sink == "appsink" else " force-aspect-ratio=true"),
        ]
        return " ! ".join(elements)

    def build(self):
        """Instancia o pipeline no GStreamer (requer Gst.init já chamado).

        Cada elemento é criado pela fábrica e os valores são atribuídos como
        propriedades, de modo que nenhum dado de entrada é interpretado como
        sintaxe de pipeline.
        """
        from gi.repository import Gst

        capture = self._validated_capture()
        strategy = strategy_for(capture.pixel_format)
        effect = self._effect

        pipeline = Gst.Pipeline.new("camview")
        elements = []

        source = self._make(Gst, "v4l2src", "source")
        source.set_property("device", capture.device)
        elements.append(source)

        caps_filter = self._make(Gst, "capsfilter", FILTER_ELEMENT)
        caps = Gst.Caps.from_string(strategy.source_caps(capture))
        if caps is None:
            raise PipelineError(f"invalid caps for {capture.pixel_format.value}")
        caps_filter.set_property("caps", caps)
        elements.append(caps_filter)

        for factory in strategy.decode_chain():
            elements.append(self._make(Gst, factory, factory))

        if self._rotation:
            rotate = self._make(Gst, "videoflip", ROTATE_ELEMENT)
            rotate.set_property("method", {90: "clockwise", 180: "rotate-180",
                                          270: "counterclockwise"}[self._rotation])
            elements.append(rotate)

        # O recorte vem antes dos filtros: menos pixels para processar, e o
        # elemento fica sempre no pipeline para trocar de contorno ao vivo.
        if crop_available():
            crop = self._make(Gst, "videocrop", CROP_ELEMENT)
            elements.append(crop)

        elements.append(self._make(Gst, "videoconvert", "convert"))

        # Cadeia de efeitos: os parâmetros de cor são propriedades, então
        # trocar de filtro não exige reconstruir o pipeline (ver apply_effect).
        if not (self._optimize_neutral and effect == NORMAL):
            balance = self._make(Gst, "videobalance", BALANCE_ELEMENT)
            gamma = self._make(Gst, "gamma", GAMMA_ELEMENT)
            elements += [balance, gamma]

        if color_effects_available() and not (self._optimize_neutral and effect == NORMAL):
            elements.append(self._make(Gst, "videoconvert", "convert-color"))
            elements.append(self._make(Gst, "coloreffects", COLOR_ELEMENT))

        if effect.element:
            elements.append(self._make(Gst, "videoconvert", "convert-fun"))
            elements.append(self._make(Gst, effect.element, FUN_ELEMENT))

        elements.append(self._make(Gst, "videoconvert", "convert-out"))

        if self._viewport is not None and digital_zoom_available():
            elements.append(self._make(Gst, "videoscale", "zoom_scale"))
            elements.append(self._make(Gst, "capsfilter", ZOOM_SIZE_ELEMENT))
            box = self._make(Gst, "videobox", ZOOM_BOX_ELEMENT)
            box.set_property("fill", 0)  # preto, sem aplicar filtros às bordas
            elements.append(box)

        flip = self._make(Gst, "videoflip", FLIP_ELEMENT)
        flip.set_property("method", "horizontal-flip" if self._mirror else "none")
        elements.append(flip)

        sink = self._make(Gst, self._sink, SINK_ELEMENT)
        if sink.find_property("force-aspect-ratio") is not None:
            sink.set_property("force-aspect-ratio", True)
        elements.append(sink)

        for element in elements:
            pipeline.add(element)
        for current, following in zip(elements, elements[1:], strict=False):
            if not current.link(following):
                raise PipelineError(
                    f"could not link {current.get_name()} → "
                    f"{following.get_name()}"
                )
        apply_effect(pipeline, effect)
        apply_crop(pipeline, self._crop)
        if self._viewport is not None:
            apply_viewport(pipeline, *self._viewport)
        return pipeline

    @staticmethod
    def _make(gst, factory: str, name: str):
        element = gst.ElementFactory.make(factory, name)
        if element is None:
            raise PipelineError(
                f"GStreamer element '{factory}' unavailable "
                "(check the gstreamer1.0-plugins-* packages)"
            )
        return element
