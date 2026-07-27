import io
import PyPDF2


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """
    Определяет формат файла по расширению и извлекает из него текст.
    """
    text = ""

    if filename.lower().endswith('.pdf'):
        # Читаем PDF из байтов в памяти
        pdf_file = io.BytesIO(file_bytes)
        reader = PyPDF2.PdfReader(pdf_file)

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

    elif filename.lower().endswith('.txt'):
        # Читаем обычный текстовый файл
        text = file_bytes.decode('utf-8')

    else:
        raise ValueError("Неподдерживаемый формат файла. Разрешены только PDF и TXT.")

    return text.strip()