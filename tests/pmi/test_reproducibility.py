"""PDFs remain ignored by Git; frozen inputs must regenerate byte for byte."""
from pmi.dataset import sha256, write_pdf


def test_generated_pdf_bytes_are_reproducible(tmp_path):
    text='Резюме\nФИО: Тестовый Кандидат\nНавыки: Python, PostgreSQL.\nОпыт работы: 3 года.'
    first,second=tmp_path/'first.pdf',tmp_path/'second.pdf'
    write_pdf(first,text)
    write_pdf(second,text)
    assert sha256(first)==sha256(second)
