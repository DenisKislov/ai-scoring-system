import json
import os

SKILLS = {
    # --- languages ---
    "Python": ["python", "питон", "пайтон", "python3"],
    "Java": ["java", "джава"],
    "JavaScript": ["javascript", "js", "джаваскрипт"],
    "TypeScript": ["typescript", "ts"],
    "Go": ["golang", "го"],
    "Kotlin": ["kotlin", "котлин"],
    "PHP": ["php", "пхп"],
    "Ruby": ["ruby", "рубин"],
    "Scala": ["scala", "скала"],
    "Swift": ["swift"],
    # --- data / query ---
    "SQL": ["sql", "эскуэль"],
    "PostgreSQL": ["postgresql", "postgres", "постгрес", "постгр"],
    "MySQL": ["mysql", "майэскьюэль"],
    "MongoDB": ["mongodb", "mongo", "монго"],
    "Redis": ["redis", "редис"],
    "ClickHouse": ["clickhouse", "кликхаус"],
    "Elasticsearch": ["elasticsearch", "эластик"],
    # --- ML / data science ---
    "Machine Learning": ["machine learning", "машинное обучение", " ml "],
    "Deep Learning": ["deep learning", "глубокое обучение", "нейросеть", "нейросети", "нейронная сеть", "нейронные сети"],
    "Data Science": ["data science", "наука о данных"],
    "NLP": ["nlp", "обработка естественного языка", "естественный язык"],
    "Computer Vision": ["computer vision", "компьютерное зрение", "цифровое зрение", "видеоаналитика", "обработка изображений", "распознавание образов", "распознавание изображений"],
    "Artificial Intelligence": ["artificial intelligence", "искусственный интеллект", " ии "],
    "Pandas": ["pandas", "пандас"],
    "NumPy": ["numpy", "нампи"],
    "scikit-learn": ["scikit-learn", "sklearn", "скикит"],
    "TensorFlow": ["tensorflow", "тензорфлоу"],
    "PyTorch": ["pytorch", "пайторч"],
    "Keras": ["keras", "керас"],
    "OpenCV": ["opencv", "open cv", "опенцв"],
    "TensorRT": ["tensorrt", "tensor rt"],
    "Recommender Systems": ["recommender systems", "recsys", "рекомендательные системы", "рекомендательная система"],
    "Matplotlib": ["matplotlib", "матплотлиб"],
    "OCR": ["ocr", "распознавание текста", "оптическое распознавание"],
    "Speech-to-Text": ["speech to text", "speech-to-text", "распознавание речи"],
    "Core ML": ["core ml", "coreml"],
    "Spark": ["apache spark", "spark", "спарк"],
    "Hadoop": ["hadoop", "хадуп"],
    "ETL": ["etl"],
    "Аналитика данных": ["аналитика данных", "анализ данных", "data analytics"],
    # --- web / backend ---
    "REST API": ["rest api", "rest", "рест"],
    "FastAPI": ["fastapi", "фастапи"],
    "Django": ["django", "джанго"],
    "Flask": ["flask", "фласк"],
    "Spring": ["spring", "спринг"],
    "React": ["react", "реакт"],
    "Angular": ["angular", "ангуляр"],
    "Vue": ["vue", "vuejs", "вью"],
    "HTML": ["html"],
    "CSS": ["css"],
    # --- infra / devops ---
    "Docker": ["docker", "докер", "контейнеризация"],
    "Kubernetes": ["kubernetes", "k8s", "кубернетес"],
    "Linux": ["linux", "линукс", "unix"],
    "Bash": ["bash", "шелл", "shell"],
    "Git": ["git", "гит"],
    "Jenkins": ["jenkins", "дженкинс"],
    "Ansible": ["ansible", "ансибл"],
    "Terraform": ["terraform", "терраформ"],
    "AWS": ["aws", "амазон"],
    "GCP": ["gcp", "google cloud"],
    # --- BI ---
    "Tableau": ["tableau", "табло"],
    "Power BI": ["power bi", "powerbi"],
    "Excel": ["excel", "эксель"],
    # --- process ---
    "Agile": ["agile", "аджайл"],
    "Scrum": ["scrum", "скрам"],
    "SQL (advanced)": ["t-sql", "plsql", "pl/sql"],
}

RAW_SKILLS = {
    "C++": ["c++", "с++"],
    "C#": ["c#", "с#"],
    ".NET": [".net"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "CI/CD": ["ci/cd", "ci cd"],
}

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_json(name: str) -> dict:
    path = os.path.join(_DIR, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    return {}


_AUTO_SKILLS = _load_json("skills_auto.json")
_AUTO_RAW = _load_json("skills_auto_raw.json")

SKILLS_ALL = {**_AUTO_SKILLS, **SKILLS}
RAW_SKILLS_ALL = {**_AUTO_RAW, **RAW_SKILLS}