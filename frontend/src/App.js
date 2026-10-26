import React, { useState, useEffect, useRef } from 'react';
import { api, API_BASE } from './api/api';
import './App.css';



// Экранирование спецсимволов регулярки (CI/CD, Node.js, 1С:ERP и т.п.)
const escapeRegex = (str) => String(str).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Подсветка совпадающих навыков в тексте резюме.
const highlightSkills = (text, fragments) => {
  if (!text) return null;

  const uniqueFragments = [...new Set(
    (fragments || [])
      .filter(Boolean)
      .map((s) => String(s).trim())
      .filter((s) => s.length > 0)
  )].sort((a, b) => b.length - a.length);

  if (uniqueFragments.length === 0) return text;

  const pattern = uniqueFragments.map(escapeRegex).join('|');

  const regex = new RegExp(
    `(?<![\\p{L}\\p{N}_])(${pattern})(?![\\p{L}\\p{N}_])`,
    'giu'
  );

  const lowerSet = new Set(uniqueFragments.map((s) => s.toLowerCase()));
  const parts = text.split(regex);

  return parts.map((part, i) =>
    lowerSet.has(part.toLowerCase()) ? (
      <mark key={i} className="skill-highlight">{part}</mark>
    ) : (
      part
    )
  );
};

// Доля навыков вакансии, которая есть у кандидата.
// Эквивалент бенчмарка: len(v_skills & rs) / len(v_skills).
const overlapRatio = (candidate) => {
  if (!candidate) return 0;
  const matched = new Set(candidate.matched_skills || []).size;
  const missing = new Set([
    ...(candidate.missing_skills || []),
    ...(candidate.missing_critical || []),
  ]).size;
  const total = matched + missing;
  return total > 0 ? matched / total : 0;
};

// Компактное отображение навыков в рейтинге.
const renderMatchedSkills = (skills, max = 5) => {
  const unique = [...new Set((skills || []).filter(Boolean))];
  if (unique.length === 0) return <span className="muted">—</span>;
  return <div className="skills-list compact-skills">
    {unique.slice(0, max).map((skill, i) => <span key={i} className="skill-tag">{skill}</span>)}
    {unique.length > max && <span className="skill-tag more" title={unique.slice(max).join(', ')}>+{unique.length - max}</span>}
  </div>;
};

function App() {
  const [vacancies, setVacancies] = useState([]);
  const [selectedVacancy, setSelectedVacancy] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const [feedbackMap, setFeedbackMap] = useState({});
  const [feedbackHistory, setFeedbackHistory] = useState([]);
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [vacancyForm, setVacancyForm] = useState({ title: "", description: "", skills: "", critical: "" });
  const [fullResumeText, setFullResumeText] = useState(null);
  const [resumeMentions, setResumeMentions] = useState([]);
  const [criticalSkills, setCriticalSkills] = useState([]);

  const [thresholdRatio, setThresholdRatio] = useState(null);

  const [stats, setStats] = useState({ vacancies: 0, resumes: 0 });

  const [logs, setLogs] = useState([]);

  const bootstrappedRef = useRef(false);
  const feedbackRequestRef = useRef(0);
  const scoringRequestRef = useRef(0);
  const resumeRequestRef = useRef(0);
  const feedbackSavingRef = useRef(false);

  const addLog = (type, message) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [{ timestamp, type, message }, ...prev.slice(0, 49)]);
  };

  const handleClearLogs = () => setLogs([]);

  const loadVacancies = async () => {
    try {
      const data = await api.getVacancies();
      setVacancies(Array.isArray(data) ? data : []);
    } catch (error) {
      addLog('ERROR', `Ошибка загрузки вакансий: ${error.message}`);
      setVacancies([]);
    }
  };

  const loadStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStats({
        vacancies: Number(data.vacancies) || 0,
        resumes: Number(data.resumes) || 0,
      });
    } catch (e) {
      addLog('ERROR', `[Статистика] Не удалось загрузить: ${e.message}`);
    }
  };

  const loadThreshold = async () => {
    try {
      const res = await fetch(`${API_BASE}/threshold`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (typeof data.value === 'number' && Number.isFinite(data.value)) {
        setThresholdRatio(data.value);
        addLog(
          'INFO',
          `[Порог] Загружен с бэкенда: ${(data.value * 100).toFixed(1)}% ` +
          `(вакансий: ${data.n_vacancies ?? '—'}, резюме: ${data.n_resumes ?? '—'})`
        );
      } else {
        setThresholdRatio(null);
        addLog(
          'WARN',
          '[Порог] На бэкенде не задан — фильтр отключён, показываются все кандидаты'
        );
      }
    } catch (e) {
      setThresholdRatio(null);
      addLog('ERROR', `[Порог] Не удалось загрузить: ${e.message}`);
    }
  };

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    loadVacancies();
    loadStats();
    loadThreshold();
    addLog('INFO', 'Приложение инициализировано. Панель мониторинга готова.');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setCriticalSkills(vacancies.find(v => v._id === selectedVacancy)?.critical_skills || []);
  }, [selectedVacancy, vacancies]);

  const changeVacancy = (id) => {
    ++scoringRequestRef.current;
    setLoading(false);
    setCandidates([]);
    closeModal();
    setSelectedVacancy(id);
  };

  useEffect(() => {
    if (!selectedCandidate || !selectedVacancy) return;
    let active = true;
    const requestId = ++feedbackRequestRef.current;
    setFeedbackHistory([]);
    const id = selectedCandidate.resume_id || selectedCandidate.candidate_id;
    const key = `${selectedVacancy}:${id}`;
    setFeedbackMap(prev => ({ ...prev, [key]: null }));
    fetch(`${API_BASE}/feedback?vacancy_id=${selectedVacancy}&resume_id=${id}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => { if (active && requestId === feedbackRequestRef.current) {
        setFeedbackMap(prev => ({ ...prev, [key]: data.decision }));
        setFeedbackHistory(data.history || []);
      } })
      .catch(e => addLog("ERROR", `Не удалось загрузить решение HR: ${e.message}`));
    return () => { active = false; };
  }, [selectedCandidate, selectedVacancy]);

  const handleUploadResumes = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) {
      addLog('WARN', 'Файлы не выбраны (выбор отменен пользователем)');
      return;
    }
    setIsUploading(true);
    addLog('INFO', `Инициализация парсинга файлов резюме: ${files.length} шт.`);

    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch(`${API_BASE}/upload_resume`, {
          method: 'POST',
          body: formData,
        });
        const data = await response.json();

        if (response.ok) {
          const skillsList = data.skills || [];
          const skillsStr = skillsList.slice(0, 5).join(', ');

          if (data.skills_count === 0) {
            addLog(
              'WARN',
              `[Пустой навыковый профиль] '${data.filename}' | Модель: ${data.model_name} | Длина: ${data.text_length} симв. | Навыки: 0`
            );
          } else {
            addLog(
              'SUCCESS',
              `[Резюме] '${data.filename}' | Длина текста: ${data.text_length} симв. (${data.file_size_bytes} Б) | Модель: ${data.model_name} | Навыки (${data.skills_count}): [${skillsStr}${data.skills_count > 5 ? '...' : ''}]`
            );
          }
        } else {
          addLog('WARN', `[WARN] Файл '${file.name}': ${data.detail || 'Ошибка валидации'}`);
        }
      } catch (error) {
        addLog('ERROR', `[Неверный путь/Сеть] Сбой обращения к бэкенду для '${file.name}': ${error.message}`);
      }
    }
    setIsUploading(false);
    event.target.value = null;
    await loadStats();
  };

  const handleUploadVacancies = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) {
      addLog('WARN', 'Файлы не выбраны (выбор отменен пользователем)');
      return;
    }
    setIsUploading(true);
    addLog('INFO', `Инициализация парсинга вакансий: ${files.length} шт.`);

    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch(`${API_BASE}/upload_vacancy`, {
          method: 'POST',
          body: formData,
        });
        const data = await response.json();

        if (response.ok) {
          const skillsList = data.skills || [];
          const skillsStr = skillsList.slice(0, 5).join(', ');

          if (data.skills_count === 0) {
            addLog(
              'WARN',
              `[Пустой навыковый профиль] '${data.filename}' | Модель: ${data.model_name} | Длина: ${data.text_length} симв. | Навыки: 0`
            );
          } else {
            addLog(
              'SUCCESS',
              `[Вакансия] '${data.filename}' | Длина текста: ${data.text_length} симв. | Модель: ${data.model_name} | Навыки (${data.skills_count}): [${skillsStr}${data.skills_count > 5 ? '...' : ''}]`
            );
          }
        } else {
          addLog('WARN', `[WARN] Вакансия '${file.name}': ${data.detail}`);
        }
      } catch (error) {
        addLog('ERROR', `[Неверный путь/Сеть] Сбой запроса для '${file.name}': ${error.message}`);
      }
    }
    await loadVacancies();
    await loadStats();
    setIsUploading(false);
    event.target.value = null;
  };

  const handleClearResumes = async () => {
    if (!window.confirm('ВНИМАНИЕ! Вы уверены, что хотите удалить ВСЕ резюме?')) return;
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/resumes/clear`, { method: 'DELETE' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (response.ok) {
        const data = await response.json();
        addLog('WARN', `Удалено резюме из базы: ${data.deleted_count}`);
        alert(`Успешно удалено резюме: ${data.deleted_count}`);
        setCandidates([]);
        ++scoringRequestRef.current;
        setLoading(false);
        closeModal();
        await loadStats();
      }
    } catch (e) { addLog('ERROR', `Ошибка удаления резюме: ${e.message}`); }
    finally { setIsUploading(false); }
  };

  const handleClearVacancies = async () => {
    if (!window.confirm('ВНИМАНИЕ! Вы уверены, что хотите удалить ВСЕ вакансии?')) return;
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/vacancies/clear`, { method: 'DELETE' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (response.ok) {
        const data = await response.json();
        addLog('WARN', `Удалено вакансий из базы: ${data.deleted_count}`);
        alert(`Успешно удалено вакансий: ${data.deleted_count}.`);
        await loadVacancies();
        await loadStats();
        changeVacancy(null);
      }
    } catch (e) { addLog('ERROR', `Ошибка удаления вакансий: ${e.message}`); }
    finally { setIsUploading(false); }
  };

  const handleGenerateSyntheticData = async () => {
    setIsUploading(true);
    addLog('INFO', 'Запрос на генерацию синтетических данных (5 вакансий, по 20 резюме)...');
    try {
      const response = await fetch(`${API_BASE}/generate_test_data?vacancies=5&resumes=20`, { method: 'POST' });
      if (response.ok) {
        addLog('SUCCESS', 'Синтетический датасет успешно сгенерирован и загружен в MongoDB');
        alert('Синтетические данные успешно созданы!');
        await loadVacancies();
        await loadStats();
      } else {
        addLog('ERROR', 'Ошибка при генерации синтетических данных');
      }
    } catch (e) {
      addLog('ERROR', `Сетевая ошибка генератора: ${e.message}`);
    } finally { setIsUploading(false); }
  };

  const handleImportSuperJobData = async () => {
    setIsUploading(true);
    addLog('INFO', 'Запрос на импорт датасета вакансий SuperJob из JSON...');
    try {
      const response = await fetch(`${API_BASE}/import_superjob_vacancies`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        addLog('SUCCESS', `Импортировано вакансий SuperJob: ${data.imported_vacancies}`);
        alert(`Успешно импортировано ${data.imported_vacancies || 'все'} вакансий SuperJob!`);
        await loadVacancies();
        await loadStats();
      } else {
        addLog('ERROR', 'Ошибка импорта: superjob_dataset.json не найден на бэкенде');
      }
    } catch (e) {
      addLog('ERROR', `Сетевая ошибка импорта: ${e.message}`);
    } finally { setIsUploading(false); }
  };

  const handleImportSuperJobResumes = async () => {
    setIsUploading(true);
    addLog('INFO', 'Запрос на импорт реального датасета резюме (dataset_resume.json)...');
    try {
      const response = await fetch(`${API_BASE}/import_superjob_resumes`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        addLog(
          'SUCCESS',
          `[Импорт резюме] Успешно загружено ${data.imported_resumes} резюме | Источник: SuperJob JSON | Модель: ${data.model_name}`
        );
        alert(`Успешно импортировано ${data.imported_resumes} резюме!`);
        await loadStats();
      } else {
        const err = await response.json();
        addLog('WARN', `[Импорт резюме] Ошибка: ${err.detail}`);
      }
    } catch (e) {
      addLog('ERROR', `[Импорт резюме] Сетевая ошибка: ${e.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleViewResumeText = async (resumeId) => {
    const requestId = ++resumeRequestRef.current;
    try {
      const response = await fetch(`${API_BASE}/resumes/${resumeId}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (response.ok) {
        const data = await response.json();
        if (requestId !== resumeRequestRef.current) return;
        const text = data._raw_text || data.formatted_text || "Текст резюме не найден в базе.";
        setResumeMentions(data.skill_mentions || []);
        setFullResumeText(text);
        addLog('INFO', `Просмотр текста резюме ID: ${resumeId.slice(-6)}`);
      }
    } catch (error) {
      addLog('ERROR', `Ошибка загрузки резюме: ${error.message}`);
    }
  };

  const handleScoring = async (vacancyId) => {
    if (!vacancyId) {
      addLog('WARN', '[Неверный путь/ID] Вакансия не выбрана. Выберите вакансию из списка');
      return;
    }

    const currentVac = vacancies.find((v) => v._id === vacancyId);
    const vacTitle = currentVac ? currentVac.title : vacancyId;
    const reqSkills = currentVac ? currentVac.skills || [] : [];
    const requestId = ++scoringRequestRef.current;

    setLoading(true);
    setCandidates([]);
    closeModal();
    addLog(
      'INFO',
      `[Старт скоринга] Вакансия: '${vacTitle}' | Требуемые навыки (${reqSkills.length}): [${reqSkills.slice(0, 5).join(', ')}${reqSkills.length > 5 ? '...' : ''}]`
    );

    try {
      const scoreRes = await fetch(`${API_BASE}/score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vacancy_id: vacancyId,
          limit_resumes: 5000,
          critical_skills: criticalSkills,
        }),
      });

      const scoreMeta = await scoreRes.json();
      if (requestId !== scoringRequestRef.current) return;

      if (!scoreRes.ok) {
        addLog('ERROR', `[Сбой модели скоринга] ${scoreMeta.detail || 'Неизвестная ошибка'}`);
        return;
      }

      // Use this run's result, not a second request that can include older rows.
      let candidatesArray = scoreMeta.results || [];
      setVacancies(prev => prev.map(v => v._id === vacancyId
        ? { ...v, critical_skills: [...criticalSkills] } : v));

      candidatesArray.sort((a, b) => {
        if (b.score !== a.score) return (b.score || 0) - (a.score || 0);
        return (b.experience_years || 0) - (a.experience_years || 0);
      });

      setCandidates(candidatesArray);

      if (thresholdRatio !== null) {
        const passed = candidatesArray.filter((c) => overlapRatio(c) >= thresholdRatio).length;
        addLog(
          'SUCCESS',
          `[Скоринг завершен] Оценено: ${candidatesArray.length} | ` +
          `Порог ${(thresholdRatio * 100).toFixed(1)}% прошли: ${passed}`
        );
      } else {
        addLog(
          'SUCCESS',
          `[Скоринг завершен] Оценено: ${candidatesArray.length} | Порог не задан`
        );
      }

    } catch (error) {
      addLog('ERROR', `[Неверный путь/Сервер недоступен] Ошибка при скоринге: ${error.message}`);
    } finally {
      if (requestId === scoringRequestRef.current) setLoading(false);
    }
  };

  const sendFeedback = async (resumeId, decision) => {
    if (feedbackSavingRef.current) return;
    feedbackSavingRef.current = true;
    setFeedbackSaving(true);
    const requestId = ++feedbackRequestRef.current;
    const vacancyId = selectedVacancy;
    const key = `${vacancyId}:${resumeId}`;
    try {
      const response = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vacancy_id: vacancyId, resume_id: resumeId, decision: decision }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (response.ok) {
        const saved = await response.json();
        if (requestId !== feedbackRequestRef.current) return;
        setFeedbackMap((prev) => ({ ...prev, [key]: decision }));
        if (saved.event) setFeedbackHistory(prev => [...prev, saved.event]);
        // Include events which may have been absent while the initial GET was in flight.
        const historyResponse = await fetch(`${API_BASE}/feedback?vacancy_id=${vacancyId}&resume_id=${resumeId}`);
        if (!historyResponse.ok) throw new Error(`HTTP ${historyResponse.status}`);
        const current = await historyResponse.json();
        if (requestId !== feedbackRequestRef.current) return;
        setFeedbackHistory(current.history || []);
        setFeedbackMap(prev => ({ ...prev, [key]: current.decision }));
        addLog('INFO', `HR фидбек: резюме ${resumeId.slice(-6)} отмечено как '${decision}'`);
      }
    } catch (error) {
      addLog('ERROR', `Ошибка отправки фидбека: ${error.message}`);
    } finally {
      if (requestId === feedbackRequestRef.current) {
        feedbackSavingRef.current = false;
        setFeedbackSaving(false);
      }
    }
  };

  const handleCandidateClick = (c) => {
    closeModal();
    setSelectedCandidate(c);
    setFullResumeText(null);
    setResumeMentions([]);
  };

  const createVacancy = async (e) => {
    e.preventDefault();
    const list = text => text.split(",").map(s => s.trim()).filter(Boolean);
    const response = await fetch(`${API_BASE}/vacancies`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: vacancyForm.title, description: vacancyForm.description,
        skills: list(vacancyForm.skills), critical_skills: list(vacancyForm.critical) })
    }).catch(error => { addLog("ERROR", error.message); return null; });
    if (!response) return;
    const data = await response.json();
    if (!response.ok) { addLog("ERROR", JSON.stringify(data.detail)); return; }
    setVacancyForm({ title: "", description: "", skills: "", critical: "" });
    await loadVacancies(); await loadStats();
    changeVacancy(data._id);
  };

  const closeModal = () => {
    ++feedbackRequestRef.current;
    ++resumeRequestRef.current;
    feedbackSavingRef.current = false;
    setFeedbackSaving(false);
    setFeedbackHistory([]);
    setSelectedCandidate(null);
    setFullResumeText(null);
    setResumeMentions([]);
  };

  const matchedNames = (selectedCandidate?.matched_skills || []).map(s => s.toLowerCase());
  const matchedFragments = [...(selectedCandidate?.matched_skills || []),
    ...resumeMentions.filter(m => matchedNames.includes(m.skill.toLowerCase())).map(m => m.text)];

  const visibleCandidates = thresholdRatio === null
    ? candidates
    : candidates.filter((c) => overlapRatio(c) >= thresholdRatio);

  const hiddenCount = candidates.length - visibleCandidates.length;

  const currentVacancyObj = vacancies.find((v) => v._id === selectedVacancy);
  const selectedResumeId = selectedCandidate?.resume_id || selectedCandidate?.candidate_id;
  const feedbackKey = `${selectedVacancy}:${selectedResumeId}`;

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-symbol" aria-hidden="true">S</span>
          <div><p className="eyebrow">Рабочее пространство HR</p><h1>Скоринг кандидатов</h1></div>
        </div>
        <div className="stats" aria-label="Документы в базе">
          <div className="stat"><strong>{stats.vacancies}</strong><span>вакансий</span></div>
          <div className="stat"><strong>{stats.resumes}</strong><span>резюме</span></div>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar" aria-label="Подготовка документов">
          <section className="panel upload-panel" aria-labelledby="documents-heading">
            <div className="section-heading"><span className="step">01</span><h2 id="documents-heading">Документы</h2></div>
            <p className="section-description">Загрузите резюме и требования вакансии.</p>
            <div className="upload-field">
              <label htmlFor="resume-upload">Резюме</label>
              <p id="resume-upload-hint">PDF или TXT · можно выбрать несколько</p>
              <input id="resume-upload" type="file" multiple accept=".pdf,.txt" onChange={handleUploadResumes}
                disabled={isUploading} aria-describedby="resume-upload-hint" />
            </div>
            <div className="upload-field">
              <label htmlFor="vacancy-upload">Вакансии</label>
              <p id="vacancy-upload-hint">PDF или TXT · с текстовым слоем</p>
              <input id="vacancy-upload" type="file" multiple accept=".pdf,.txt" onChange={handleUploadVacancies}
                disabled={isUploading} aria-describedby="vacancy-upload-hint" />
            </div>
            {isUploading && <p className="upload-status" role="status">Загрузка документов...</p>}

            <details className="vacancy-form-panel">
              <summary>Создать вакансию</summary>
              <form onSubmit={createVacancy} className="vacancy-form">
                {[
                  ['title', 'Название вакансии'], ['description', 'Описание вакансии'],
                  ['skills', 'Навыки через запятую'], ['critical', 'Критические навыки через запятую']
                ].map(([key, label]) => <label key={key}>{label}
                  <input required={key === 'title'} value={vacancyForm[key]}
                    onChange={e => setVacancyForm({ ...vacancyForm, [key]: e.target.value })} />
                </label>)}
                <button type="submit" className="button-primary">Сохранить вакансию</button>
              </form>
            </details>
            <div className="data-actions">
              <p className="field-label">Управление данными</p>
              <button className="button-quiet" onClick={handleClearResumes} disabled={isUploading}
                title="Удалить все резюме и связанные результаты">Удалить резюме</button>
              <button className="button-quiet" onClick={handleClearVacancies} disabled={isUploading}
                title="Удалить все вакансии и связанные результаты">Удалить вакансии</button>
            </div>
          </section>
        </aside>

        <main className="main-content">
          <section className="panel vacancies" aria-labelledby="vacancy-heading">
            <div className="section-heading"><span className="step">02</span><h2 id="vacancy-heading">Параметры отбора</h2></div>
            <div className="scoring-controls">
              <div className="vacancy-select">
                <label htmlFor="vacancy-select">Вакансия</label>
                <select id="vacancy-select" value={selectedVacancy || ''} onChange={(e) => changeVacancy(e.target.value)} disabled={isUploading}>
                  <option value="">Выберите вакансию</option>
                  {Array.isArray(vacancies) && vacancies.map((v) => (
                    <option key={v._id} value={v._id}>{`${v.title} (ID: ${v._id.slice(-4)})`}</option>
                  ))}
                </select>
              </div>
              <button className="button-primary scoring-button" onClick={() => handleScoring(selectedVacancy)}
                disabled={!selectedVacancy || loading || isUploading}>
                {loading ? 'Загрузка...' : 'Рассчитать скоринг'}
              </button>
            </div>
            {currentVacancyObj && currentVacancyObj.skills && currentVacancyObj.skills.length > 0 && (
              <fieldset className="critical-skills">
                <legend>Критические навыки <span>Вес ×2</span></legend>
                <div className="skills-options">
                  {currentVacancyObj.skills.map((skill) => (
                    <label key={skill} className={`skill-option${criticalSkills.includes(skill) ? ' selected' : ''}`}>
                      <input type="checkbox" disabled={loading} checked={criticalSkills.includes(skill)}
                        onChange={(e) => {
                          if (e.target.checked) setCriticalSkills([...criticalSkills, skill]);
                          else setCriticalSkills(criticalSkills.filter(s => s !== skill));
                        }} />
                      <span>{skill}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </section>

          <section className="panel results" aria-labelledby="results-heading" aria-busy={loading}>
            <div className="results-header">
              <div className="section-heading"><span className="step">03</span><h2 id="results-heading">Рейтинг кандидатов</h2></div>
              <div className="results-actions">
                {Array.isArray(candidates) && candidates.length > 0 && (
                  <span className="count">{visibleCandidates.length} кандидатов{thresholdRatio !== null && hiddenCount > 0 && ` из ${candidates.length}`}</span>
                )}
                {selectedVacancy && <a href={`${API_BASE}/results/${selectedVacancy}`} target="_blank" rel="noreferrer" download="results.json">Выгрузить JSON</a>}
              </div>
            </div>
            <div className="table-wrapper">
              {!Array.isArray(candidates) || candidates.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-symbol" aria-hidden="true">—</div>
                  <h3>{loading ? 'Рассчитываем рейтинг' : 'Нет результатов'}</h3>
                  <p>{loading ? 'Дождитесь завершения расчёта.' : 'Выберите вакансию и нажмите «Рассчитать скоринг»'}</p>
                </div>
              ) : visibleCandidates.length === 0 ? (
                <div className="empty-state"><h3>Нет подходящих кандидатов</h3>
                  <p>Ни один из {candidates.length} кандидатов не прошёл отбор по совпадению навыков.</p></div>
              ) : (
                <table>
                  <thead><tr><th scope="col">#</th><th scope="col">Кандидат</th><th scope="col">Score</th><th scope="col">Найденные ключевые навыки</th></tr></thead>
                  <tbody>
                    {visibleCandidates.map((c, index) => (
                      <tr key={c.resume_id || c._id || index} tabIndex={0} onClick={() => handleCandidateClick(c)}
                        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleCandidateClick(c); } }}>
                        <td className="rank">#{index + 1}</td>
                        <td className="candidate-name"><strong>{c.candidate_name || c.position || 'Кандидат'}</strong></td>
                        <td className="score-cell"><span>{c.score || 0}%</span></td>
                        <td className="candidate-skills">{renderMatchedSkills(c.matched_skills, 5)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </main>
      </div>

      <div className="support-grid">
        <section className="panel activity-panel" aria-labelledby="activity-heading">
          <div className="support-heading"><h2 id="activity-heading">Журнал действий</h2>
            <button className="button-link" onClick={handleClearLogs}>очистить</button></div>
          <div className="activity-log" aria-label="Логи выполнения" role="log">
            {logs.length === 0 ? <p className="muted">Логи пока пусты...</p> : logs.map((log, index) => (
              <div key={index} className={`log-entry log-${log.type.toLowerCase()}`}>
                <time>{log.timestamp}</time><span className="log-type">{log.type}</span><span>{log.message}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel tools-panel" aria-labelledby="tools-heading">
          <h2 id="tools-heading">Тестовые данные</h2>
          <p className="section-description">Для проверки работы системы.</p>
          <button className="button-secondary" onClick={handleGenerateSyntheticData} disabled={isUploading}>Синтетический генератор</button>
          <p className="tool-hint">5 вакансий · 100 резюме</p>
          {process.env.REACT_APP_ENABLE_EXTERNAL_IMPORTS === 'true' && <div className="external-imports">
            <button onClick={handleImportSuperJobData} disabled={isUploading}>Вакансии SuperJob</button>
            <button onClick={handleImportSuperJobResumes} disabled={isUploading}>Резюме SuperJob</button>
          </div>}
        </section>
      </div>
      <footer className="app-footer"><span>Система оценки соответствия резюме вакансии</span>
        <nav aria-label="Служебные ссылки"><a href={`${API_BASE}/config`} target="_blank" rel="noreferrer">Конфигурация алгоритма</a>
          <a href={`${API_BASE}/logs?lines=200`} target="_blank" rel="noreferrer">Журнал API</a></nav>
      </footer>

      {selectedCandidate && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="candidate-heading" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={closeModal} title="Закрыть карточку">✕</button>
            <p className="eyebrow">Карточка кандидата</p>
            <h2 id="candidate-heading">{selectedCandidate.candidate_name || selectedCandidate.position || 'Кандидат'}</h2>
            <div className="modal-grid">
              <div className="modal-item"><span className="field-label">Score</span><span className="modal-score">{selectedCandidate.score || 0}%</span></div>
              <div className="modal-item"><span className="field-label">Опыт</span><span>{selectedCandidate.experience_years || 0} лет</span></div>
            </div>
            <div className="modal-grid contributions" aria-label="Вклад компонентов">
              <div className="modal-item"><span className="field-label">Вклад навыков</span><span>{((selectedCandidate.keyword_contribution || 0) * 100).toFixed(1)} п. п.</span></div>
              <div className="modal-item"><span className="field-label">Вклад сходства текстов</span><span>{((selectedCandidate.cosine_contribution || 0) * 100).toFixed(1)} п. п.</span></div>
            </div>
            <div className="modal-skills"><h3>Совпадающие навыки</h3><div className="skills-list">
              {[...new Set(selectedCandidate.matched_skills || [])].map((skill, i) => <span key={i} className="skill-tag">{skill}</span>)}
              {[...new Set(selectedCandidate.matched_skills || [])].length === 0 && <span className="muted">Нет совпадений</span>}
            </div></div>
            {selectedCandidate.missing_critical && selectedCandidate.missing_critical.length > 0 && (
              <div className="modal-skills"><h3>Критические пробелы:</h3><div className="skills-list">
                {selectedCandidate.missing_critical.map((skill, i) => <span key={i} className="skill-tag critical">{skill}</span>)}
              </div></div>
            )}
            <div className="modal-skills"><h3>Остальные недостающие навыки</h3><div className="skills-list">
              {(selectedCandidate.missing_skills || []).map((skill, i) => <span key={i} className="skill-tag missing">{skill}</span>)}
            </div></div>
            <div className="resume-section">
              {!fullResumeText ? <button className="button-secondary resume-toggle" onClick={() => handleViewResumeText(selectedResumeId)}>Посмотреть текст резюме</button> : (
                <div><div className="support-heading"><h3>Оригинальный текст:</h3><button className="button-link" onClick={() => setFullResumeText(null)}>Скрыть</button></div>
                  <div className="resume-text">{highlightSkills(fullResumeText, matchedFragments)}</div></div>
              )}
            </div>
            <div className="feedback-section">
              <p className="feedback-decision">Решение HR: {feedbackMap[feedbackKey] === 'yes' ? 'Да' : feedbackMap[feedbackKey] === 'no' ? 'Нет' : 'Не задано'}</p>
              <div className="modal-feedback">
                <button className="button-secondary" disabled={feedbackSaving} aria-pressed={feedbackMap[feedbackKey] === 'yes'} onClick={() => sendFeedback(selectedResumeId, 'yes')}>Да</button>
                <button className="button-secondary" disabled={feedbackSaving} aria-pressed={feedbackMap[feedbackKey] === 'no'} onClick={() => sendFeedback(selectedResumeId, 'no')}>Нет</button>
              </div>
              <ul className="feedback-history" aria-label="История решений HR">{feedbackHistory.map((item, index) =>
                <li key={item._id || index}>{item.decision === 'yes' ? 'Да' : 'Нет'} — {new Date(item.updated_at).toLocaleString()}</li>
              )}</ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
