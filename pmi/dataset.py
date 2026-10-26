"""Frozen synthetic PDF corpus. Labels precede rendering and scoring.

Five independent professional directions, ten vacancies, 200 resumes. This is a
controlled acceptance corpus; the noisier six-role benchmark remains separate.
No real resumes, no label-derived skills are passed into the scoring kernel.
"""
from __future__ import annotations
import hashlib
import json
import random
from pathlib import Path
import fitz

SEED = 1729
PROFILES = {
    'Разработка ПО': ('Разработчик программного обеспечения',
        ['Python', 'Django', 'FastAPI', 'PostgreSQL', 'Docker', 'Git', 'Redis', 'pytest']),
    'Бухгалтерия': ('Бухгалтер',
        ['1С: Бухгалтерия', 'РСБУ', 'МСФО', 'НДС', 'Налоговый учёт', 'Бухгалтерская отчётность', 'Расчёт заработной платы', 'Банк-клиент']),
    'Продажи': ('Менеджер по продажам',
        ['B2B Продажи', 'Холодные звонки', 'Работа с возражениями', 'Навыки переговоров', 'Заключение договоров', 'Ведение клиентской базы', 'Salesforce', 'Битрикс24']),
    'Маркетинг': ('Маркетолог',
        ['Яндекс Директ', 'Google Ads', 'SEO', 'Веб-аналитика', 'Яндекс Метрика', 'Контент-маркетинг', 'A/B-тестирование', 'Email-маркетинг']),
    'Проектирование': ('Инженер-конструктор',
        ['AutoCAD', 'КОМПАС', 'SolidWorks', 'ЕСКД', 'Чтение чертежей', 'Расчёт прочности', 'Проектирование механизмов', 'Технические расчёты']),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_pdf(path: Path, text: str) -> None:
    # Built-in Droid fallback supports Cyrillic and is identical in containers.
    font = fitz.Font('cjk')
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_font(fontname='pmi', fontbuffer=font.buffer)
        overflow = page.insert_textbox(fitz.Rect(40, 35, 555, 805), text,
                                      fontsize=10, fontname='pmi', lineheight=1.3)
        if overflow < 0:
            raise ValueError('Synthetic PDF does not fit on one page')
        doc.subset_fonts()
        # Dates and IDs are fixed, so byte hashes can be reproduced.
        doc.set_metadata({'title': 'Synthetic acceptance document', 'producer': 'PMI dataset 1'})
        doc.save(path, garbage=4, deflate=True, no_new_id=True)


def generate(root: Path) -> dict:
    rng = random.Random(SEED)
    root.mkdir(parents=True, exist_ok=True)
    for kind in ['vacancies', 'resumes', 'controls']:
        (root/kind).mkdir(exist_ok=True)
    vacancies, resumes = [], []
    for direction, (role, stack) in PROFILES.items():
        for index in range(2):
            required = list(stack) if index == 0 else stack[2:] + stack[:1]
            critical = required[:2]
            vid = f'v{len(vacancies)+1:03}'
            text = (f'Вакансия: {role}\nСинтетическая организация. Направление: {direction}.\n\n'
                    'Команда развивает действующий продукт и ищет специалиста.\n'
                    'Задачи: решать профильные задачи, проверять результат, согласовывать изменения с коллегами.\n'
                    'Требования:\n' + '\n'.join('- ' + s for s in required) + '\n'
                    'Критические требования: ' + ', '.join(critical) + '.\n'
                    'Опыт работы: от 2 лет.\nУсловия: гибридный график, планирование задач, обратная связь.')
            item = {'id': vid, 'direction': direction, 'title': role, 'skills': required,
                    'critical_skills': critical, 'text': text, 'file': f'vacancies/{vid}.pdf'}
            write_pdf(root/item['file'], text)
            vacancies.append(item)
        for index in range(40):
            # A fixed spread of experience and abilities, independent of scores.
            size = rng.choice([1,2,3,4,5,6,7,8])
            latent = sorted(rng.sample(stack, size))
            visible = list(latent)
            # Controlled omissions; these do not alter latent relevance labels.
            if len(visible) >= 4 and index % 5 == 0:
                visible.pop(rng.randrange(len(visible)))
            years = rng.randint(0, 12)
            rid = f'r{len(resumes)+1:03}'
            text = (f'Резюме\nФИО: Тестовый Кандидат {rid}\n'
                    f'Специализация: {role}\nГород: Тестовый город\n\n'
                    'О себе: умею разбирать задачи, проверять результат и обсуждать решения с командой.\n\n'
                    f'Опыт работы: {years} лет.\n'
                    'Место работы: синтетическая организация.\n'
                    'Работа включала выполнение профильных задач, подготовку материалов,\n'
                    'проверку изменений и передачу результата коллегам.\n'
                    'Достижение: сокращено время выполнения регулярных задач.\n\n'
                    'Ключевые навыки:\n' + '\n'.join('- '+s for s in visible) + '\n\n'
                    'Образование: профильная программа и самостоятельные проекты.\n'
                    'Формат работы: гибридный. Данные вымышлены для испытаний.')
            item = {'id':rid, 'direction':direction, 'title':role, 'latent_skills':latent,
                    'text_skills':visible, 'experience_years':years, 'text':text,
                    'file':f'resumes/{rid}.pdf'}
            write_pdf(root/item['file'], text)
            resumes.append(item)
    pairs = []
    for vacancy in vacancies:
        for resume in resumes:
            # Explicit specification: weighted latent skill coverage. Experience
            # is a tiebreak only. No extraction, TF-IDF or model output is used.
            required, critical, latent = set(vacancy['skills']), set(vacancy['critical_skills']), set(resume['latent_skills'])
            relevance = sum(2 if s in critical else 1 for s in required & latent) / (len(required) + len(critical))
            pairs.append({'vacancy_id':vacancy['id'], 'resume_id':resume['id'], 'relevance':relevance})
    controls = {
        'aliases': 'Специализация: Разработчик\nНавыки: PostgreSQL, Postgres, постгрес, psql, JS, JavaScript, k8s, Kubernetes.',
        'critical_all': 'Специализация: Разработчик\nНавыки: Python, PostgreSQL.\nОпыт работы: 3 года.',
        'critical_none': 'Специализация: Разработчик\nНавыки: Docker, Git.\nОпыт работы: 3 года.',
        'personal_a': 'ФИО: Тестовый Кандидат А\nВозраст: 25\nПол: мужской\nАдрес: Тестовый город А\nГражданство: Тестовая страна А\nНавыки: Python, PostgreSQL, Docker.\nОпыт работы: 3 года.',
        'personal_b': 'ФИО: Тестовый Кандидат Б\nВозраст: 53\nПол: женский\nАдрес: Тестовый город Б\nГражданство: Тестовая страна Б\nНавыки: Python, PostgreSQL, Docker.\nОпыт работы: 3 года.',
    }
    for name, text in controls.items():
        write_pdf(root/'controls'/f'{name}.pdf', text)
    (root/'controls/empty.txt').write_bytes(b'')
    (root/'controls/broken.pdf').write_bytes(b'%PDF-1.7\nnot a valid document')
    (root/'controls/unsupported.doc').write_bytes(b'not a supported format')
    with fitz.open() as doc:
        doc.new_page()
        doc.save(root/'controls/no_text.pdf', no_new_id=True)
    dataset = {'version':'pmi-synthetic-1', 'seed':SEED,
               'label_definition':'weighted latent skill coverage; critical=2; ordinary=1',
               'synthetic':True, 'vacancies':vacancies, 'resumes':resumes, 'pairs':pairs}
    (root/'dataset.json').write_text(json.dumps(dataset, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return dataset


def freeze(root: Path) -> dict:
    from scorer.config import algorithm_manifest
    project = Path(__file__).resolve().parents[1]
    sources = []
    for folder in ['api','scorer','db','pmi','frontend/src']:
        sources.extend(p for p in (project/folder).rglob('*') if p.suffix in ['.py','.js','.css','.json'] and '__pycache__' not in p.parts)
    sources += [project/'docker-compose.yml', project/'backend.Dockerfile', project/'frontend/Dockerfile',project/'frontend/package-lock.json']
    manifest = {'source_files':{str(p.relative_to(project)):sha256(p) for p in sorted(sources)},
                'algorithm':algorithm_manifest(), 'dataset_files':
                {str(p.relative_to(root)):sha256(p) for p in sorted(root.rglob('*'))
                 if p.is_file() and p.name != 'manifest.json'}}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def verify(root: Path) -> dict:
    from scorer.config import algorithm_manifest
    manifest = json.loads((root/'manifest.json').read_text())
    errors = [name for name, digest in manifest['dataset_files'].items()
              if not (root/name).is_file() or sha256(root/name) != digest]
    project = Path(__file__).resolve().parents[1]
    errors += ['source: '+name for name,digest in manifest.get('source_files',{}).items()
               if not (project/name).is_file() or sha256(project/name) != digest]
    if manifest['algorithm']['fingerprint'] != algorithm_manifest()['fingerprint']:
        errors.append('algorithm fingerprint changed')
    return {'ok':not errors, 'errors':errors}


def restore_missing(root: Path) -> list[str]:
    """Recreate ignored PDFs in a clean checkout without replacing the manifest.

    Every regenerated byte is compared with the already-frozen hash before any
    file is installed. Existing, modified inputs are never silently repaired.
    """
    import shutil
    import tempfile
    manifest = json.loads((root/'manifest.json').read_text())
    missing = [name for name in manifest['dataset_files'] if not (root/name).exists()]
    if not missing:
        return []
    with tempfile.TemporaryDirectory(prefix='pmi-regenerate-') as temporary:
        stage = Path(temporary)
        generate(stage)
        for name in missing:
            candidate = stage/name
            if not candidate.is_file() or sha256(candidate) != manifest['dataset_files'][name]:
                raise ValueError(f'Regenerated input differs from frozen hash: {name}; use the pinned runtime or start a new protocol')
        for name in missing:
            destination=root/name
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(stage/name,destination)
    return missing
