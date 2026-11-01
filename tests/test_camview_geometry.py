import pytest

from camview.config import PHONE_ASPECT, Corner
from camview.geometry import (
    MIN_WINDOW_WIDTH,
    Rect,
    centered_crop,
    clamp_radius,
    corner_origin,
    crop_borders,
    edge_at,
    scaled_size,
    sized_by_height,
    zoomed_content,
    zoomed_crop,
)

WORKAREA = Rect(x=0, y=0, width=1920, height=1080)


def test_corner_origin_top_left():
    assert corner_origin(WORKAREA, 320, 180, Corner.TOP_LEFT, 16) == (16, 16)


def test_corner_origin_bottom_right():
    x, y = corner_origin(WORKAREA, 320, 180, Corner.BOTTOM_RIGHT, 16)
    assert (x, y) == (1920 - 320 - 16, 1080 - 180 - 16)


def test_corner_origin_respects_workarea_offset():
    area = Rect(x=100, y=50, width=800, height=600)
    assert corner_origin(area, 200, 100, Corner.TOP_LEFT, 10) == (110, 60)
    expected = (100 + 800 - 210, 50 + 600 - 110)
    assert corner_origin(area, 200, 100, Corner.BOTTOM_RIGHT, 10) == expected


def test_scaled_size_keeps_aspect_ratio():
    width, height = scaled_size(640, 1280, 720, 1.5)
    assert width == 960
    assert height == round(960 * 720 / 1280)


def test_scaled_size_enforces_minimum_width():
    width, _ = scaled_size(90, 1280, 720, 0.5)
    assert width == MIN_WINDOW_WIDTH


def test_clamp_radius_limits_to_half_smallest_side():
    assert clamp_radius(500, 400, 200) == 100
    assert clamp_radius(20, 400, 200) == 20
    assert clamp_radius(-5, 400, 200) == 0


def test_inscribed_circle_landscape():
    from camview.geometry import inscribed_circle

    assert inscribed_circle(1280, 720) == (640, 360, 360)
    assert inscribed_circle(400, 400) == (200, 200, 200)


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (200, 100, None),  # interior
        (5, 100, "west"),
        (395, 100, "east"),
        (200, 5, "north"),
        (200, 195, "south"),
        (5, 5, "north-west"),
        (395, 5, "north-east"),
        (5, 195, "south-west"),
        (395, 195, "south-east"),
    ],
)
def test_edge_at(x, y, expected):
    assert edge_at(x, y, 400, 200, 14) == expected


def test_edge_at_boundary_is_exclusive():
    assert edge_at(14, 100, 400, 200, 14) is None
    assert edge_at(386, 100, 400, 200, 14) is None


def test_centered_crop_portrait_from_landscape():
    """1280x720 vira um retrato 9:16 com a mesma altura, centrado."""
    crop = centered_crop(1280, 720, PHONE_ASPECT)
    assert (crop.width, crop.height) == (404, 720)  # 405 arredondado para par
    assert crop.x == (1280 - 404) // 2
    assert crop.y == 0


def test_centered_crop_never_exceeds_the_capture():
    for width, height in ((640, 480), (720, 1280), (1920, 1080), (800, 600)):
        crop = centered_crop(width, height, PHONE_ASPECT)
        assert 0 < crop.width <= width
        assert 0 < crop.height <= height
        assert crop.x + crop.width <= width
        assert crop.y + crop.height <= height


def test_centered_crop_uses_even_coordinates():
    """Formatos YUV subamostrados não aceitam recorte em pixel ímpar."""
    crop = centered_crop(1281, 721, PHONE_ASPECT)
    assert crop.x % 2 == crop.y % 2 == crop.width % 2 == crop.height % 2 == 0


def test_centered_crop_of_a_taller_capture_cuts_the_height():
    crop = centered_crop(720, 1280, PHONE_ASPECT)
    assert crop.width == 720
    assert crop.height == 1280  # 720x1280 já é 9:16
    crop = centered_crop(600, 1600, PHONE_ASPECT)
    assert (crop.width, crop.height) == (600, 1066)
    assert crop.x == 0


def test_centered_crop_rejects_invalid_aspect():
    with pytest.raises(ValueError):
        centered_crop(1280, 720, (0, 16))


def test_crop_borders_complete_the_frame():
    crop = centered_crop(1280, 720, PHONE_ASPECT)
    left, right, top, bottom = crop_borders(1280, 720, crop)
    assert left + crop.width + right == 1280
    assert top + crop.height + bottom == 720
    assert left == right  # centrado
    assert (top, bottom) == (0, 0)


def test_sized_by_height_keeps_the_height_when_the_aspect_changes():
    """Ao virar retrato a janela mantém a altura, em vez de estourar a tela."""
    width, height = sized_by_height(360, 404, 720)
    assert height == 360
    assert width == round(360 * 404 / 720)


def test_sized_by_height_enforces_minimum_width():
    width, height = sized_by_height(40, 404, 720)
    assert width == MIN_WINDOW_WIDTH
    assert height == round(MIN_WINDOW_WIDTH * 720 / 404)


def test_digital_zoom_reset_restores_the_entire_frame():
    frame = Rect(0, 0, 1280, 720)
    assert zoomed_crop(frame, 2) == Rect(320, 180, 640, 360)
    assert zoomed_crop(frame, 4) == Rect(480, 270, 320, 180)
    assert zoomed_crop(frame, 1) == frame


@pytest.mark.parametrize("zoom", [0.25, 0.5, 1, 1.05, 1.5, 2, 3, 4])
@pytest.mark.parametrize("size", [(1280, 720), (3840, 2160), (1281, 721), (16, 8)])
def test_digital_zoom_stays_inside_phone_crop_with_even_alignment(zoom, size):
    frame = centered_crop(*size, PHONE_ASPECT)
    crop = zoomed_crop(frame, zoom)
    assert frame.x <= crop.x < crop.x + crop.width <= frame.x + frame.width
    assert frame.y <= crop.y < crop.y + crop.height <= frame.y + frame.height
    assert all(value % 2 == 0 for value in (crop.x, crop.y, crop.width, crop.height))
    assert abs(crop.x + crop.width / 2 - (frame.x + frame.width / 2)) <= 2
    assert abs(crop.y + crop.height / 2 - (frame.y + frame.height / 2)) <= 2


def test_digital_zoom_preserves_a_minimum_yuv_frame():
    assert zoomed_crop(Rect(0, 0, 2, 2), 4) == Rect(0, 0, 2, 2)


@pytest.mark.parametrize("zoom", [0, 0.24, 4.01, -1, float("nan"), float("inf")])
def test_digital_zoom_rejects_invalid_values(zoom):
    with pytest.raises(ValueError, match="invalid digital zoom"):
        zoomed_crop(Rect(0, 0, 1280, 720), zoom)


@pytest.mark.parametrize(
    ("zoom", "expected"),
    [(0.25, Rect(480, 270, 320, 180)), (0.5, Rect(320, 180, 640, 360)),
     (1, Rect(0, 0, 1280, 720)), (4, Rect(0, 0, 1280, 720))],
)
def test_zoom_out_content_is_centered_in_the_original_viewport(zoom, expected):
    assert zoomed_content(1280, 720, zoom) == expected
    assert zoomed_crop(Rect(0, 0, 1280, 720), min(zoom, 1)) == Rect(0, 0, 1280, 720)


@pytest.mark.parametrize("size", [(1281, 721), (404, 720), (2, 2)])
@pytest.mark.parametrize("zoom", [0.25, 0.5, 0.95])
def test_zoom_out_preserves_output_size_and_yuv_alignment(size, zoom):
    width, height = size
    content = zoomed_content(width, height, zoom)
    left, right, top, bottom = crop_borders(width, height, content)
    assert all(value >= 0 for value in (left, right, top, bottom))
    assert content.width > 0 and content.height > 0
    assert content.width + left + right == width
    assert content.height + top + bottom == height
    assert all(value % 2 == 0 for value in
               (content.x, content.y, content.width, content.height))


@pytest.mark.parametrize("args", [(0, 720, 0.5), (1280, -1, 0.5), (1280, 720, 0.2)])
def test_zoom_out_rejects_invalid_viewport_or_zoom(args):
    with pytest.raises(ValueError):
        zoomed_content(*args)
