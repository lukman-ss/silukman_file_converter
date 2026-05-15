# silukman_file_converter - Test Input Pack

Paket ini berisi file input untuk menguji aplikasi `silukman_file_converter`.

## Isi Paket

- `01_pdf_text_layer/`
  PDF yang memiliki selectable text. Gunakan untuk test direct text extraction, split PDF, compress PDF, protect PDF, PDF to image.

- `02_pdf_scan_no_text_layer/`
  PDF image-only tanpa text layer. Gunakan untuk membuktikan OCR PDF scan benar-benar memakai PaddleOCR.

- `03_images_for_ocr/`
  Gambar dokumen sintetis untuk test OCR: invoice, nota, surat jalan, dokumen rotated, blur, dan low-resolution table.

- `04_images_for_converter/`
  Gambar PNG/JPG/JPEG sederhana untuk test image to PDF.

- `05_office_files/`
  DOCX, XLSX, dan PPTX untuk test konversi office document.

- `06_html/`
  HTML sederhana untuk test HTML to PDF.

- `07_expected_results/expected_keywords.json`
  Keyword yang harus muncul pada hasil OCR atau direct text extraction.

## Aturan Test yang Disarankan

Jangan tandai test sebagai sukses hanya karena output file berhasil dibuat.

Validasi minimal:

- output file exists
- output file size > 0
- output file can be opened
- output format matches target
- page count valid for PDF
- image can be opened for image output
- OCR text length reasonable
- expected keywords found
- confidence score reasonable

## OCR Test Penting

Gunakan file berikut untuk OCR:

- `03_images_for_ocr/invoice_clean.png`
- `03_images_for_ocr/nota_blur.jpg`
- `03_images_for_ocr/surat_jalan_rotated.png`
- `03_images_for_ocr/table_lowres.jpg`
- `02_pdf_scan_no_text_layer/invoice_scan_no_text_layer.pdf`
- `02_pdf_scan_no_text_layer/multipage_scan_no_text_layer.pdf`

PDF di folder `02_pdf_scan_no_text_layer` tidak memiliki selectable text. Jika hasil OCR keluar dari file tersebut, berarti pipeline render PDF to image + PaddleOCR berjalan.

## File Publik dari Internet

Paket ini menyertakan PDF publik untuk kebutuhan test text-layer PDF:

- PDFObject sample PDF
- W3C dummy PDF

Dokumen OCR seperti invoice, nota, dan surat jalan dibuat sintetis agar aman dan sesuai studi kasus aplikasi.
