from pathlib import Path
import importlib
import os

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


class ImageService:
    def image_to_pdf(self, image_path: str, output_dir: str, output_prefix: str = "") -> Path:
        source = Path(image_path)
        output = Path(output_dir) / f"{output_prefix}{source.stem}.pdf"

        with Image.open(source) as image:
            rgb_image = image.convert("RGB")
            rgb_image.save(output, "PDF", resolution=100.0)

        return output

    def preprocess_for_ocr(self, image_path: str, output_dir: str) -> Path:
        cv_stack = self._load_cv_stack()
        if cv_stack is None:
            return self._preprocess_for_ocr_pillow(image_path, output_dir)

        cv2, np = cv_stack
        source = Path(image_path)
        output = Path(output_dir) / f"{source.stem}_preprocessed.png"

        image = cv2.imread(str(source))
        if image is None:
            raise ValueError(f"Gagal membaca gambar: {source}")

        image = self._upscale_if_needed(image)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        normalized = self._normalize_contrast(gray)
        denoised = cv2.fastNlMeansDenoising(normalized, None, 7, 7, 21)
        deskewed = self._deskew(denoised)
        cv2.imwrite(str(output), deskewed)

        return output

    def preprocess_variants_for_ocr(self, image_path: str, output_dir: str) -> list[Path]:
        cv_stack = self._load_cv_stack()
        if cv_stack is None:
            return self._preprocess_variants_for_ocr_pillow(image_path, output_dir)

        cv2, np = cv_stack
        source = Path(image_path)
        image = cv2.imread(str(source))
        if image is None:
            raise ValueError(f"Gagal membaca gambar: {source}")

        variants: list[tuple[str, np.ndarray]] = []
        variants.append(("original", image))

        upscaled = self._upscale_if_needed(image)
        gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
        normalized = self._normalize_contrast(gray)
        variants.append(("upscaled_contrast", normalized))

        denoised = cv2.fastNlMeansDenoising(normalized, None, 7, 7, 21)
        variants.append(("gray_denoise", denoised))

        thresholded = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            11,
        )
        variants.append(("adaptive_threshold", thresholded))

        outputs = []
        for name, variant in variants:
            output = Path(output_dir) / f"{source.stem}_{name}.png"
            cv2.imwrite(str(output), variant)
            outputs.append(output)
        return outputs

    def _load_cv_stack(self):
        if os.environ.get("SILUKMAN_DISABLE_CV2_PREPROCESS") == "1":
            return None
        try:
            return importlib.import_module("cv2"), importlib.import_module("numpy")
        except ImportError:
            return None

    def _preprocess_for_ocr_pillow(self, image_path: str, output_dir: str) -> Path:
        source = Path(image_path)
        output = Path(output_dir) / f"{source.stem}_preprocessed.png"
        image = self._pillow_base_image(source)
        image.save(output)
        return output

    def _preprocess_variants_for_ocr_pillow(self, image_path: str, output_dir: str) -> list[Path]:
        source = Path(image_path)
        base = self._pillow_base_image(source)
        variants = [
            ("original", Image.open(source).convert("RGB")),
            ("upscaled_contrast", base),
            ("gray_denoise", base.filter(ImageFilter.MedianFilter(size=3))),
            ("threshold", base.point(lambda value: 255 if value > 175 else 0)),
        ]

        outputs = []
        for name, image in variants:
            output = Path(output_dir) / f"{source.stem}_{name}.png"
            image.save(output)
            outputs.append(output)
        return outputs

    def _pillow_base_image(self, source: Path, min_width: int = 1200, upscale_factor: int = 2) -> Image.Image:
        with Image.open(source) as raw:
            image = ImageOps.exif_transpose(raw).convert("L")
        width, height = image.size
        if width < min_width:
            factor = max(upscale_factor, (min_width + max(width, 1) - 1) // max(width, 1))
            image = image.resize((width * factor, height * factor), Image.Resampling.BICUBIC)
        image = ImageOps.autocontrast(image)
        return ImageEnhance.Contrast(image).enhance(1.4)

    def _upscale_if_needed(self, image, min_width: int = 1200, upscale_factor: int = 2):
        cv2, np = self._load_cv_stack()
        height, width = image.shape[:2]
        if width >= min_width:
            return image
        factor = max(upscale_factor, int(np.ceil(min_width / max(width, 1))))
        return cv2.resize(image, (width * factor, height * factor), interpolation=cv2.INTER_CUBIC)

    def _normalize_contrast(self, gray):
        cv2, _ = self._load_cv_stack()
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _deskew(self, gray):
        cv2, np = self._load_cv_stack()
        coords = np.column_stack(np.where(gray < 245))
        if len(coords) < 32:
            return gray
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.4 or abs(angle) > 10:
            return gray
        height, width = gray.shape[:2]
        matrix = cv2.getRotationMatrix2D((width // 2, height // 2), angle, 1.0)
        return cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
