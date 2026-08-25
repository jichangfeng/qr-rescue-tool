from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Callable, Iterable

import cv2
import numpy as np
import zxingcpp


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class DecodeResult:
    text: str
    method: str
    version: int | None = None
    error_correction: str = ""
    timing_score: float | None = None


@dataclass(frozen=True)
class _Finder:
    center: np.ndarray
    module_px: float
    score: float


@dataclass(frozen=True)
class _Geometry:
    top_left: np.ndarray
    top_right: np.ndarray
    bottom_left: np.ndarray
    version: int
    timing_score: float
    finder_score: float


# QR alignment-pattern center coordinates from ISO/IEC 18004.
_ALIGNMENT_CENTERS: tuple[tuple[int, ...], ...] = (
    (),
    (),
    (6, 18),
    (6, 22),
    (6, 26),
    (6, 30),
    (6, 34),
    (6, 22, 38),
    (6, 24, 42),
    (6, 26, 46),
    (6, 28, 50),
    (6, 30, 54),
    (6, 32, 58),
    (6, 34, 62),
    (6, 26, 46, 66),
    (6, 26, 48, 70),
    (6, 26, 50, 74),
    (6, 30, 54, 78),
    (6, 30, 56, 82),
    (6, 30, 58, 86),
    (6, 34, 62, 90),
    (6, 28, 50, 72, 94),
    (6, 26, 50, 74, 98),
    (6, 30, 54, 78, 102),
    (6, 28, 54, 80, 106),
    (6, 32, 58, 84, 110),
    (6, 30, 58, 86, 114),
    (6, 34, 62, 90, 118),
    (6, 26, 50, 74, 98, 122),
    (6, 30, 54, 78, 102, 126),
    (6, 26, 52, 78, 104, 130),
    (6, 30, 56, 82, 108, 134),
    (6, 34, 60, 86, 112, 138),
    (6, 30, 58, 86, 114, 142),
    (6, 34, 62, 90, 118, 146),
    (6, 30, 54, 78, 102, 126, 150),
    (6, 24, 50, 76, 102, 128, 154),
    (6, 28, 54, 80, 106, 132, 158),
    (6, 32, 58, 84, 110, 136, 162),
    (6, 26, 54, 82, 110, 138, 166),
    (6, 30, 58, 86, 114, 142, 170),
)


def load_image(path: str | Path) -> np.ndarray:
    """Read an image from a path, including paths containing Chinese characters."""
    raw = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("无法读取图片；请确认文件格式和路径是否有效。")
    return normalize_image(image)


def normalize_image(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise ValueError("图片为空。")
    if image.ndim == 2:
        return image.astype(np.uint8, copy=False)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if image.shape[2] == 3:
        return image.astype(np.uint8, copy=False)
    raise ValueError("不支持该图片的颜色格式。")


def decode_image(
    image: np.ndarray,
    progress: ProgressCallback | None = None,
) -> DecodeResult | None:
    image = normalize_image(image)
    notify = progress or (lambda _message: None)

    notify("正在尝试普通解码…")
    result = _standard_decode(image)
    if result:
        return result

    notify("普通解码失败，正在增强对比度和补充静区…")
    result = _enhanced_standard_decode(image)
    if result:
        return result

    notify("正在搜索定位框和时序线…")
    gray = _to_gray(image)
    geometries = _find_geometries(gray)
    if not geometries:
        return None

    for index, geometry in enumerate(geometries[:6], start=1):
        notify(
            f"正在重建二维码网格 {index}/{min(6, len(geometries))} "
            f"(Version {geometry.version})…"
        )
        result = _reconstruct_and_decode(gray, geometry)
        if result:
            return result
    return None


def decode_path(
    path: str | Path,
    progress: ProgressCallback | None = None,
) -> DecodeResult | None:
    return decode_image(load_image(path), progress=progress)


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _zxing_decode(image: np.ndarray, method: str) -> DecodeResult | None:
    try:
        barcodes = zxingcpp.read_barcodes(
            image,
            formats=zxingcpp.BarcodeFormat.QRCode,
            try_rotate=True,
            try_downscale=True,
            try_invert=True,
        )
    except Exception:
        return None
    for barcode in barcodes:
        if barcode.valid and barcode.text:
            return DecodeResult(
                text=barcode.text,
                method=method,
                error_correction=str(barcode.ec_level or ""),
            )
    return None


def _opencv_decode(image: np.ndarray, method: str) -> DecodeResult | None:
    try:
        detector = cv2.QRCodeDetector()
        text, _points, _straight = detector.detectAndDecode(image)
    except Exception:
        return None
    if text:
        return DecodeResult(text=text, method=method)
    return None


def _standard_decode(image: np.ndarray) -> DecodeResult | None:
    result = _zxing_decode(image, "ZXing 普通解码")
    if result:
        return result
    return _opencv_decode(image, "OpenCV 普通解码")


def _white_pad(image: np.ndarray, amount: int) -> np.ndarray:
    if image.ndim == 2:
        value: int | tuple[int, int, int] = 255
    else:
        value = (255, 255, 255)
    return cv2.copyMakeBorder(
        image,
        amount,
        amount,
        amount,
        amount,
        cv2.BORDER_CONSTANT,
        value=value,
    )


def _enhanced_standard_decode(image: np.ndarray) -> DecodeResult | None:
    gray = _to_gray(image)
    short_side = min(gray.shape[:2])
    pad = max(24, int(round(short_side * 0.10)))
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    _threshold, otsu = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    adaptive = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        _odd_at_least(max(31, short_side // 7)),
        3,
    )
    variants = (
        ("灰度补白", _white_pad(gray, pad)),
        ("局部对比度增强", _white_pad(clahe, pad)),
        ("Otsu 二值化", _white_pad(otsu, pad)),
        ("自适应二值化", _white_pad(adaptive, pad)),
    )
    for name, variant in variants:
        for scale in (1, 2):
            candidate = variant
            if scale == 2:
                candidate = cv2.resize(
                    variant, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST
                )
            result = _zxing_decode(candidate, name)
            if result:
                return result
            result = _opencv_decode(candidate, name)
            if result:
                return result
    return None


def _odd_at_least(value: int) -> int:
    value = max(3, int(value))
    return value if value % 2 else value + 1


def _finder_template(module_px: float) -> np.ndarray:
    pattern = np.zeros((9, 9), dtype=np.float32)
    pattern[1:8, 1:8] = 1.0
    pattern[2:7, 2:7] = 0.0
    pattern[3:6, 3:6] = 1.0
    size = max(9, int(round(9 * module_px)))
    template = cv2.resize(pattern, (size, size), interpolation=cv2.INTER_NEAREST)
    return cv2.GaussianBlur(template, (0, 0), max(0.45, module_px * 0.10))


def _candidate_module_sizes(gray: np.ndarray) -> Iterable[float]:
    short_side = min(gray.shape[:2])
    low = max(1.35, short_side / 650.0)
    high = max(low + 0.2, short_side / 18.0)
    value = low
    while value <= high:
        yield value
        value *= 1.055


def _collect_finders(gray: np.ndarray) -> list[_Finder]:
    height, width = gray.shape
    max_side = max(height, width)
    scale = min(1.0, 1000.0 / max_side)
    if scale < 1.0:
        work = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        work = gray
    inverted = 255 - work
    raw_candidates: list[_Finder] = []

    for module_px in _candidate_module_sizes(work):
        template = _finder_template(module_px)
        th, tw = template.shape
        if th >= work.shape[0] or tw >= work.shape[1]:
            continue
        response = cv2.matchTemplate(
            inverted.astype(np.float32), template, cv2.TM_CCOEFF_NORMED
        )
        local = response.copy()
        for _ in range(8):
            _minimum, score, _minimum_location, location = cv2.minMaxLoc(local)
            if score < 0.53:
                break
            center = np.array(
                [location[0] + tw / 2.0, location[1] + th / 2.0], dtype=float
            )
            raw_candidates.append(_Finder(center, module_px, float(score)))
            radius = max(5, int(round(4.0 * module_px)))
            x1 = max(0, location[0] - radius)
            y1 = max(0, location[1] - radius)
            x2 = min(local.shape[1], location[0] + radius)
            y2 = min(local.shape[0], location[1] + radius)
            local[y1:y2, x1:x2] = -1.0

    clustered: list[_Finder] = []
    for candidate in sorted(raw_candidates, key=lambda item: item.score, reverse=True):
        if any(
            np.linalg.norm(candidate.center - kept.center)
            < max(6.0, 1.8 * max(candidate.module_px, kept.module_px))
            for kept in clustered
        ):
            continue
        clustered.append(candidate)
        if len(clustered) >= 32:
            break

    if scale != 1.0:
        clustered = [
            _Finder(item.center / scale, item.module_px / scale, item.score)
            for item in clustered
        ]
    return clustered


def _sample_patch(gray: np.ndarray, point: np.ndarray, radius: int) -> float:
    x, y = float(point[0]), float(point[1])
    size = 2 * radius + 1
    if x < radius or y < radius or x >= gray.shape[1] - radius or y >= gray.shape[0] - radius:
        return 255.0
    patch = cv2.getRectSubPix(gray, (size, size), (x, y))
    return float(np.median(patch))


def _timing_score(
    gray: np.ndarray,
    top_left: np.ndarray,
    top_right: np.ndarray,
    bottom_left: np.ndarray,
    version: int,
) -> float:
    modules = 17 + 4 * version
    distance = modules - 7
    horizontal = (top_right - top_left) / distance
    vertical = (bottom_left - top_left) / distance
    module_px = (np.linalg.norm(horizontal) + np.linalg.norm(vertical)) / 2.0
    radius = 0 if module_px < 3.0 else 1
    values: list[float] = []
    expected: list[float] = []

    for coordinate in range(8, modules - 8):
        point = top_left + (coordinate - 3) * horizontal + 3 * vertical
        values.append(_sample_patch(gray, point, radius))
        expected.append(1.0 if coordinate % 2 == 0 else -1.0)
    for coordinate in range(8, modules - 8):
        point = top_left + 3 * horizontal + (coordinate - 3) * vertical
        values.append(_sample_patch(gray, point, radius))
        expected.append(1.0 if coordinate % 2 == 0 else -1.0)

    observed = -np.asarray(values, dtype=float)
    wanted = np.asarray(expected, dtype=float)
    if observed.size < 8 or float(np.std(observed)) < 1e-6:
        return -1.0
    return float(np.corrcoef(observed, wanted)[0, 1])


def _ordered_right_triangle(
    points: tuple[_Finder, _Finder, _Finder]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float] | None:
    locations = [point.center for point in points]
    best: tuple[np.ndarray, np.ndarray, np.ndarray, float] | None = None
    for corner_index in range(3):
        corner = locations[corner_index]
        arms = [locations[index] - corner for index in range(3) if index != corner_index]
        lengths = [float(np.linalg.norm(arm)) for arm in arms]
        if min(lengths) < 20.0 or max(lengths) / min(lengths) > 1.65:
            continue
        cosine = float(np.dot(arms[0], arms[1]) / (lengths[0] * lengths[1]))
        if abs(cosine) > 0.36:
            continue
        first, second = arms
        # Use the scalar 2-D determinant explicitly.  NumPy 2.0 deprecated
        # np.cross for two-component vectors and newer releases reject it.
        cross = float(first[0] * second[1] - first[1] * second[0])
        if cross > 0:
            horizontal, vertical = first, second
        else:
            horizontal, vertical = second, first
        geometry_score = 1.0 - abs(cosine) - abs(lengths[0] - lengths[1]) / max(lengths)
        candidate = (corner, corner + horizontal, corner + vertical, geometry_score)
        if best is None or candidate[3] > best[3]:
            best = candidate
    return best


def _find_geometries(gray: np.ndarray) -> list[_Geometry]:
    finders = _collect_finders(gray)
    if len(finders) < 3:
        return []

    geometries: list[_Geometry] = []
    for triple in combinations(finders[:24], 3):
        pitch_values = [item.module_px for item in triple]
        if max(pitch_values) / min(pitch_values) > 1.7:
            continue
        ordered = _ordered_right_triangle(triple)
        if ordered is None:
            continue
        top_left, top_right, bottom_left, triangle_score = ordered
        arm_length = (
            np.linalg.norm(top_right - top_left)
            + np.linalg.norm(bottom_left - top_left)
        ) / 2.0
        estimated_distance = arm_length / float(np.median(pitch_values))
        estimated_version = int(round((estimated_distance - 14.0) / 4.0)) + 1
        versions = range(max(1, estimated_version - 4), min(40, estimated_version + 4) + 1)
        best_version = 0
        best_timing = -1.0
        for version in versions:
            score = _timing_score(
                gray, top_left, top_right, bottom_left, version
            )
            if score > best_timing:
                best_version = version
                best_timing = score
        if best_timing < 0.42:
            continue
        finder_score = sum(item.score for item in triple) / 3.0
        geometries.append(
            _Geometry(
                top_left=top_left,
                top_right=top_right,
                bottom_left=bottom_left,
                version=best_version,
                timing_score=best_timing,
                finder_score=finder_score + 0.10 * triangle_score,
            )
        )

    geometries.sort(
        key=lambda item: item.timing_score + 0.35 * item.finder_score,
        reverse=True,
    )
    unique: list[_Geometry] = []
    for geometry in geometries:
        if any(
            geometry.version == kept.version
            and np.linalg.norm(geometry.top_left - kept.top_left) < 8.0
            for kept in unique
        ):
            continue
        unique.append(geometry)
    return unique


def _alignment_template(module_px: float) -> np.ndarray:
    pattern = np.zeros((7, 7), dtype=np.float32)
    pattern[1:6, 1:6] = 1.0
    pattern[2:5, 2:5] = 0.0
    pattern[3, 3] = 1.0
    size = max(7, int(round(7 * module_px)))
    template = cv2.resize(pattern, (size, size), interpolation=cv2.INTER_NEAREST)
    return cv2.GaussianBlur(template, (0, 0), max(0.40, module_px * 0.10))


def _find_alignment_controls(
    gray: np.ndarray,
    geometry: _Geometry,
) -> tuple[np.ndarray, np.ndarray]:
    modules = 17 + 4 * geometry.version
    distance = modules - 7
    horizontal = (geometry.top_right - geometry.top_left) / distance
    vertical = (geometry.bottom_left - geometry.top_left) / distance
    module_px = (np.linalg.norm(horizontal) + np.linalg.norm(vertical)) / 2.0

    source: list[tuple[float, float]] = [
        (3.0, 3.0),
        (float(modules - 4), 3.0),
        (3.0, float(modules - 4)),
    ]
    destination: list[np.ndarray] = [
        geometry.top_left,
        geometry.top_right,
        geometry.bottom_left,
    ]
    if geometry.version == 1:
        return np.asarray(source), np.asarray(destination)

    inverted = 255 - gray
    centers = _ALIGNMENT_CENTERS[geometry.version]
    for y in centers:
        for x in centers:
            if (x < 10 and y < 10) or (x > modules - 11 and y < 10) or (
                x < 10 and y > modules - 11
            ):
                continue
            predicted = (
                geometry.top_left
                + (x - 3) * horizontal
                + (y - 3) * vertical
            )
            best_score = -1.0
            best_center: np.ndarray | None = None
            for factor in (0.88, 0.96, 1.04, 1.12):
                template = _alignment_template(module_px * factor)
                th, tw = template.shape
                search_radius = max(8, int(round(module_px * 2.8)))
                left = max(0, int(round(predicted[0] - tw / 2 - search_radius)))
                top = max(0, int(round(predicted[1] - th / 2 - search_radius)))
                right = min(
                    gray.shape[1], int(round(predicted[0] + tw / 2 + search_radius))
                )
                bottom = min(
                    gray.shape[0], int(round(predicted[1] + th / 2 + search_radius))
                )
                roi = inverted[top:bottom, left:right]
                if roi.shape[0] < th or roi.shape[1] < tw:
                    continue
                response = cv2.matchTemplate(
                    roi.astype(np.float32), template, cv2.TM_CCOEFF_NORMED
                )
                _minimum, score, _minimum_location, location = cv2.minMaxLoc(response)
                if score > best_score:
                    best_score = float(score)
                    best_center = np.array(
                        [left + location[0] + tw / 2, top + location[1] + th / 2],
                        dtype=float,
                    )
            if best_center is not None and best_score >= 0.43:
                source.append((float(x), float(y)))
                destination.append(best_center)
    return np.asarray(source), np.asarray(destination)


def _features(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.stack((np.ones_like(x), x, y, x * y, x * x, y * y), axis=-1)


def _fit_mapping(
    source: np.ndarray,
    destination: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, bool]:
    if len(source) >= 6:
        matrix = _features(source[:, 0], source[:, 1])
        x_coefficients = np.linalg.lstsq(matrix, destination[:, 0], rcond=None)[0]
        y_coefficients = np.linalg.lstsq(matrix, destination[:, 1], rcond=None)[0]
        residuals = np.linalg.norm(
            np.column_stack((matrix @ x_coefficients, matrix @ y_coefficients))
            - destination,
            axis=1,
        )
        if len(source) >= 8:
            cutoff = max(2.5, float(np.median(residuals)) * 2.5)
            keep = residuals <= cutoff
            if int(np.sum(keep)) >= 6 and not bool(np.all(keep)):
                matrix = matrix[keep]
                kept_destination = destination[keep]
                x_coefficients = np.linalg.lstsq(
                    matrix, kept_destination[:, 0], rcond=None
                )[0]
                y_coefficients = np.linalg.lstsq(
                    matrix, kept_destination[:, 1], rcond=None
                )[0]
        return x_coefficients, y_coefficients, True

    # With only the three finder centers, an affine mapping is the safest fallback.
    matrix = np.column_stack((np.ones(len(source)), source[:, 0], source[:, 1]))
    return (
        np.linalg.lstsq(matrix, destination[:, 0], rcond=None)[0],
        np.linalg.lstsq(matrix, destination[:, 1], rcond=None)[0],
        False,
    )


def _rectify(
    gray: np.ndarray,
    geometry: _Geometry,
    source: np.ndarray,
    destination: np.ndarray,
    samples_per_module: int,
) -> np.ndarray:
    modules = 17 + 4 * geometry.version
    x_coefficients, y_coefficients, quadratic = _fit_mapping(source, destination)
    out_y, out_x = np.mgrid[
        0 : modules * samples_per_module,
        0 : modules * samples_per_module,
    ].astype(np.float32)
    module_x = (out_x + 0.5) / samples_per_module - 0.5
    module_y = (out_y + 0.5) / samples_per_module - 0.5
    if quadratic:
        feature_grid = _features(module_x, module_y)
    else:
        feature_grid = np.stack(
            (np.ones_like(module_x), module_x, module_y), axis=-1
        )
    map_x = np.tensordot(feature_grid, x_coefficients, axes=([-1], [0])).astype(
        np.float32
    )
    map_y = np.tensordot(feature_grid, y_coefficients, axes=([-1], [0])).astype(
        np.float32
    )
    return cv2.remap(
        gray,
        map_x,
        map_y,
        cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _with_quiet_zone(image: np.ndarray, samples_per_module: int) -> np.ndarray:
    return _white_pad(image, 4 * samples_per_module)


def _reconstruct_and_decode(
    gray: np.ndarray,
    geometry: _Geometry,
) -> DecodeResult | None:
    source, destination = _find_alignment_controls(gray, geometry)
    distance = 17 + 4 * geometry.version - 7
    horizontal_pitch = np.linalg.norm(geometry.top_right - geometry.top_left) / distance
    vertical_pitch = np.linalg.norm(geometry.bottom_left - geometry.top_left) / distance
    observed_pitch = (horizontal_pitch + vertical_pitch) / 2.0
    samples_per_module = int(np.clip(round(observed_pitch * 1.8), 8, 14))
    rectified = _rectify(
        gray, geometry, source, destination, samples_per_module
    )

    def return_with_details(result: DecodeResult | None, method: str) -> DecodeResult | None:
        if result is None:
            return None
        return DecodeResult(
            text=result.text,
            method=method,
            version=geometry.version,
            error_correction=result.error_correction,
            timing_score=geometry.timing_score,
        )

    direct = _zxing_decode(
        _with_quiet_zone(rectified, samples_per_module), "网格纠偏（灰度）"
    )
    detailed = return_with_details(direct, "定位框 + 网格纠偏")
    if detailed:
        return detailed

    modules = 17 + 4 * geometry.version
    block_modules = (5, 7, 9, 11, 13, 15)
    constants = (0, -4, 4, -8, 8, -12, 12)
    for block_count in block_modules:
        block_size = _odd_at_least(block_count * samples_per_module)
        max_block = min(rectified.shape[:2])
        if block_size >= max_block:
            block_size = _odd_at_least(max_block - 2)
        for constant in constants:
            binary = cv2.adaptiveThreshold(
                rectified,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                block_size,
                constant,
            )
            result = _zxing_decode(
                _with_quiet_zone(binary, samples_per_module),
                "网格纠偏 + 自适应二值化",
            )
            detailed = return_with_details(
                result, "定位框 + 时序线 + 校正点重建"
            )
            if detailed:
                return detailed

            module_grid = np.empty((modules, modules), dtype=np.uint8)
            margin = max(1, samples_per_module // 5)
            for row in range(modules):
                for column in range(modules):
                    cell = binary[
                        row * samples_per_module + margin : (row + 1)
                        * samples_per_module
                        - margin,
                        column * samples_per_module + margin : (column + 1)
                        * samples_per_module
                        - margin,
                    ]
                    module_grid[row, column] = 255 if float(np.mean(cell)) > 127 else 0
            crisp = cv2.resize(
                module_grid,
                None,
                fx=samples_per_module,
                fy=samples_per_module,
                interpolation=cv2.INTER_NEAREST,
            )
            result = _zxing_decode(
                _with_quiet_zone(crisp, samples_per_module), "逐模块重建"
            )
            detailed = return_with_details(result, "逐模块重建")
            if detailed:
                return detailed
    return None
