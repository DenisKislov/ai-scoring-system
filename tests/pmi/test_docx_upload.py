"""A Word document uses the same upload and scoring path as PDF and TXT."""
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from api.file_parser import extract_text_from_file

WORD_XML = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def make_docx(body):
    package = BytesIO()
    with ZipFile(package, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="' + DOCX_TYPE + '.main+xml"/></Types>')
        archive.writestr('_rels/.rels',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', body)
    return package.getvalue()


def document(body):
    return make_docx(f'<w:document xmlns:w="{WORD_XML}"><w:body>{body}</w:body></w:document>')


def test_docx_upload_and_scoring(client):
    vacancy = document('<w:p><w:r><w:t>Требования: Python и PostgreSQL.</w:t></w:r></w:p>')
    resume = document(
        '<w:p><w:r><w:t>Опыт работы: 3 года.</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Навыки: Py</w:t></w:r>'
        '<w:r><w:t>thon</w:t><w:tab/><w:t>Postgres</w:t><w:br/>'
        '<w:t>Без опыта Docker.</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')

    upload = client.post('/upload_vacancy', files={'file': ('vacancy.DOCX', vacancy, DOCX_TYPE)},
                         data={'critical_skills': '["Python"]'})
    assert upload.status_code == 201
    vacancy_id = upload.json()['vacancy_id']
    assert set(upload.json()['skills']) == {'Python', 'PostgreSQL'}

    batch = client.post('/upload_resumes', files=[
        ('files', ('resume.docx', resume, DOCX_TYPE)),
        ('files', ('resume.txt', b'Skills: Python.', 'text/plain')),
        ('files', ('broken.docx', b'not a zip', DOCX_TYPE)),
    ])
    assert batch.status_code == 201
    assert batch.json()['count'] == 2
    assert [row['filename'] for row in batch.json()['errors']] == ['broken.docx']
    resume_id = batch.json()['results'][0]['resume_id']
    assert set(batch.json()['results'][0]['skills']) == {'Python', 'PostgreSQL'}
    assert client.get('/resumes/' + resume_id).json()['experience_years'] == 3

    scored = client.post('/score', json={'vacancy_id': vacancy_id})
    assert scored.status_code == 200
    first = scored.json()['results'][0]
    assert first['resume_id'] == resume_id
    assert set(first['matched_skills']) == {'Python', 'PostgreSQL'}
    assert client.get('/files/resumes/' + resume_id).content == resume


@pytest.mark.parametrize(('content', 'message'), [
    (document('<w:p/>'), 'Текст в документе не обнаружен'),
    (make_docx('<document/>'), 'DOCX повреждён'),
    (make_docx(f'<!DOCTYPE w:document [<!ENTITY sample "abc">]>'
               f'<w:document xmlns:w="{WORD_XML}"><w:body><w:p><w:r><w:t>&sample;</w:t>'
               '</w:r></w:p></w:body></w:document>'), 'DOCX повреждён'),
])
def test_docx_rejects_invalid_or_empty_documents(content, message):
    with pytest.raises(ValueError, match=message):
        extract_text_from_file(content, 'example.docx')
