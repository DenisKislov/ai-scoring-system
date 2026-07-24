# HH_PARSE — Парсер вакансий и резюме HH.ru

Парсер на основе Scrapy, который собирает **вакансии**, **компании** и **резюме соискателей** с [hh.ru](https://hh.ru) (крупнейшей российской платформы по поиску работы) и сохраняет их в MongoDB.

## Возможности

- **Парсинг вакансий** — заголовок, зарплата, описание, требуемые навыки, компания-работодатель
- **Парсинг компаний** — переход на страницы работодателей для сбора информации о компании
- **Парсинг резюме** — заголовок, желаемая зарплата, специализация, возраст, пол, местоположение, общий опыт работы, языки
- **Пагинация** — автоматический обход всех страниц результатов поиска
- **Хранилище MongoDB** — все элементы сохраняются в локальном экземпляре MongoDB

> **Примечание по резюме:** hh.ru скрывает часть каждого резюме (имя соискателя и конкретные теги навыков) за авторизацией работодателя. Паук собирает все общедоступные поля; запустите его с аутентификацией, чтобы также получать навыки.

## Структура проекта
```
Parser/   (Scrapy project name: HH_PARSE)
├── main.py                         # Entry point (run from the Parser/ folder)
├── scrapy.cfg                      # Scrapy project config (default settings module)
├── config/
│   └── config.json                 # What to parse + start_urls (vacancy/company/resume toggles)
├── requirements.txt
├── README.md
├── print_from_mongodb.py           # Debug helper: count vacancies + print title/salary from Mongo
├── extract_years_of_experience.py  # Offline helper: parse "Опыт работы: N лет" from resumes.json
├── *.json                          # Generated dumps (resumes/vacancies/extracted_*) — see "Utility scripts"
└── gb_parse/
    ├── __init__.py
    ├── items.py                    # Scrapy Item definitions (vacancy, company, resume)
    ├── loaders.py                  # ItemLoaders with field processors
    ├── middlewares.py              # Spider & downloader middlewares
    ├── pipelines.py                # MongoDB storage pipeline
    ├── settings.py                 # Scrapy settings
    ├── main.py                     # Alternative entry point (run from inside gb_parse/)
    └── spiders/
        ├── __init__.py
        └── hh.py                   # HhSpider — the main spider
```


## Настройка

### 1. Установка зависимостей

```bash
pip install -r requirements.txt

2. Установка и запуск MongoDB
bash
# Ubuntu/Debian
sudo apt install mongodb
sudo systemctl start mongodb

# Или с использованием Docker
docker run -d -p 27017:27017 --name mongo mongo
docker run создает контейнер один раз. Впоследствии запускайте/останавливайте существующий контейнер: docker start mongo / docker stop mongo.

Как запустить через терминал
Вариант A — Использование main.py (корень проекта)
bash
cd /path/to/HH_PARSE
python main.py

Вариант B — Использование main.py (внутри пакета)
bash
cd /path/to/HH_PARSE/gb_parse
python main.py

Вариант C — Использование интерфейса командной строки Scrapy
bash
cd /path/to/HH_PARSE
scrapy crawl hh

Все три варианта дают одинаковый результат — паук начинает обход hh.ru и сохраняет данные в MongoDB.

Быстрый тест (опционально)
Ограничьте обход и запишите результаты в JSON-файл вместо MongoDB — удобно, когда Mongo не запущен:

bash
# Обойти несколько страниц, записать элементы в out.json, отключить конвейер Mongo
scrapy crawl hh -s CLOSESPIDER_PAGECOUNT=8 -s ITEM_PIPELINES={} -O out.json
Конфигурация
Что парсить — config/config.json
Это основной конфигурационный файл — отредактируйте его, чтобы выбрать, что будет парситься и с чего начинать обход:

Поле	Значение по умолчанию	Описание
vacancy_parsing	true	Переход на страницы деталей вакансий
company_parsing	true	Переход на страницы работодателей и сохранение элементов компаний
resume_parsing	true	Переход на страницы деталей резюме
start_urls	(см. файл)	Список URL-адресов поиска hh.ru для старта
Установите любой флаг *_parsing в false, чтобы пропустить этот тип сущностей. Паук автоматически определяет тип поиска по каждому URL — https://hh.ru/search/resume?... обходит резюме, https://hh.ru/search/vacancy?... обходит вакансии. Если файл конфигурации отсутствует или поврежден, используются встроенные настройки по умолчанию.

Настройки Scrapy и MongoDB — gb_parse/settings.py
Настройка	Значение по умолчанию	Описание
MONGO_URI	mongodb://localhost:27017	URI подключения к MongoDB
MONGO_DB	gb_parse	Имя базы данных MongoDB
DOWNLOAD_DELAY	1.5	Задержка между запросами (секунды)
CONCURRENT_REQUESTS	32	Максимальное количество одновременных запросов
Результат
Данные сохраняются в MongoDB:

Коллекция hh — элементы вакансий с полями: url, title, salary, description, skills, author_url, author_name, tags

Коллекция hh_companies — элементы компаний: url, title, description, site, external_id

Коллекция hh_resumes — элементы резюме: url, title, salary, specialization, age, gender, address, experience, skills, languages, relocation, tags

Работа с MongoDB
Все примеры используют контейнер Docker с именем mongo. При необходимости сначала запустите его: docker start mongo.

Подсчет документов
bash
docker exec -i mongo mongosh --quiet gb_parse --eval "db.hh.countDocuments()"            # вакансии
docker exec -i mongo mongosh --quiet gb_parse --eval "db.hh_companies.countDocuments()"  # компании
docker exec -i mongo mongosh --quiet gb_parse --eval "db.hh_resumes.countDocuments()"    # резюме

Экспорт коллекции в JSON
Используйте -i (не -it) и --quiet. Флаг -t подключает TTY, из-за чего mongosh
записывает управляющие последовательности терминала (заголовок/баннер) в перенаправленный файл и
повреждает JSON — именно это раньше загрязняло дампы *.json.
bash
docker exec -i mongo mongosh --quiet gb_parse --eval "JSON.stringify(db.hh.find().toArray())"          > vacancies.json
docker exec -i mongo mongosh --quiet gb_parse --eval "JSON.stringify(db.hh_resumes.find().toArray())"  > resumes.json

Удаление документов
bash
docker exec -i mongo mongosh --quiet gb_parse --eval "db.hh.deleteMany({})"            # все вакансии
docker exec -i mongo mongosh --quiet gb_parse --eval "db.hh_companies.deleteMany({})"  # все компании
docker exec -i mongo mongosh --quiet gb_parse --eval "db.hh_resumes.deleteMany({})"    # все резюме
docker exec -i mongo mongosh --quiet gb_parse --eval "db.dropDatabase()"               # все базы данных

Вспомогательные скрипты и JSON-дампы
Это опциональные вспомогательные утилиты и сгенерированные артефакты — не являются частью самого обхода.
Файл	Что делает
print_from_mongodb.py	Небольшой отладочный скрипт: подключается к gb_parse, выводит количество вакансий и title/salary каждой вакансии.
extract_years_of_experience.py	Вспомогательный скрипт для работы офлайн, который читает дамп resumes.json и извлекает общий опыт работы в годах с помощью регулярного выражения Опыт работы:\s*(\d+)\s*(лет|год|года) → extracted_experience.json.
Примечание. В рабочем конвейере опыт работы в годах теперь извлекается напрямую из MongoDB с помощью db.builders.experience_years (без необходимости в JSON-дампе) и используется для разрешения конфликтов среди кандидатов с одинаковым рейтингом — см. корневой README.md. extract_years_of_experience.py сохранен как отдельный офлайн-вариант.

JSON-дампы (*.json)
resumes.json / vacancies.json / extracted_experience.json — это восстанавливаемые артефакты, созданные приведенными выше командами экспорта (или вспомогательным скриптом извлечения лет) — не исходные файлы. Если дамп выглядит поврежденным (начинается с текста терминала mongosh …), он был экспортирован с -it; повторно экспортируйте с -i --quiet (см. "Экспорт коллекции в JSON"). Пустые файлы можно безопасно удалять.