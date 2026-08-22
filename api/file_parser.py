import fitz
import re

def extract_text_from_file(content: bytes, filename: str) -> str:
    if filename.lower().endswith('.pdf'):
        text_blocks = []

        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            blocks = page.get_text("blocks")
            for block in blocks:
                text = block[4]
                if text.strip():
                    text_blocks.append(text.strip())

        full_text = "\n".join(text_blocks)

        clean_text = re.sub(r'(?<=[a-zа-яё])(?=[A-ZА-ЯЁ])', ' ', full_text)
        clean_text = re.sub(r'(?<=[a-zа-яё])(?=[0-9])', ' ', clean_text)
        clean_text = re.sub(r'\n+', '\n', clean_text)

        return clean_text.strip()

    elif filename.lower().endswith('.txt'):
        return content.decode('utf-8', errors='ignore').strip()

    raise ValueError("Неподдерживаемый формат файла. Загрузите PDF или TXT.")