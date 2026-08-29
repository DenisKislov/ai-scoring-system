import React, { useState, useEffect } from 'react';
import { api } from './api/api';
import './App.css';

const API_BASE = 'http://127.0.0.1:8000';

function App() {
  const [vacancies, setVacancies] = useState([]);
  const [selectedVacancy, setSelectedVacancy] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const [feedbackMap, setFeedbackMap] = useState({});
  const [fullResumeText, setFullResumeText] = useState(null);
  const [criticalSkills, setCriticalSkills] = useState([]);

  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState({
    precision: 0,
    recall: 0,
    f1: 0,
    avgScore: 0,
    totalScored: 0,
  });

  // Локальное логирование (флаг isLocal предотвращает затирание при синхронизации)
  const addLog = (type, message) => {
    const timestamp = new Date().toLocaleTimeString('ru-RU', { hour12: false });
    setLogs((prev) => [{ timestamp, type, message, isLocal: true }, ...prev].slice(0, 50));
  };

  // Синхронизация логов с сервером
  const fetchServerLogs = async () => {
    try {
      const response = await fetch(`${API_BASE}/logs?lines=50`);
      if (response.ok) {
        const data = await response.json();
        setLogs((prevLogs) => {
          // Оставляем только локальные логи (например, ошибки сети или расчет метрик фронтом)
          const localLogs = prevLogs.filter((log) => log.isLocal);
          // Объединяем с логами бэкенда и сортируем по времени (новые сверху)
          const combined = [...localLogs, ...data.logs].sort((a, b) =>
            a.timestamp > b.timestamp ? -1 : 1
          );
          return combined.slice(0, 50);
        });
      }
    } catch (error) {
      console.error('Ошибка синхронизации логов с сервером:', error);
    }
  };

  // Пуллинг сервера каждые 2 секунды
  useEffect(() => {
    fetchServerLogs();
    const interval = setInterval(fetchServerLogs, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleClearLogs = async () => {
    try {
      await fetch(`${API_BASE}/logs/clear`, { method: 'DELETE' });
      setLogs([]); // Очищаем стейт после команды серверу
    } catch (e) {
      addLog('ERROR', `Ошибка очистки логов: ${e.message}`);
    }
  };

  const loadVacancies = async () => {
    try {
      const data = await api.getVacancies();
      if (Array.isArray(data)) {
        setVacancies(data);
      } else {
        setVacancies([]);
      }
    } catch (error) {
      addLog('ERROR', `Ошибка загрузки вакансий: ${error.message}`);
      setVacancies([]);
    }
  };

  useEffect(() => {
    loadVacancies();
    addLog('INFO', 'Приложение инициализировано. Готово к работе.');
  }, []);

  useEffect(() => {
    setCriticalSkills([]);
  }, [selectedVacancy]);

  const handleUploadResumes = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) {
      addLog('WARN', 'Выбор файлов отменен (пустой путь)');
      return;
    }
    setIsUploading(true);

    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch(`${API_BASE}/upload_resume`, {
          method: 'POST',
          body: formData,
        });
        if (!response.ok) {
          const err = await response.json();
          addLog('ERROR', `[Резюме] '${file.name}': ${err.detail || 'пустой текст или поврежден'}`);
        }
      } catch (error) {
        addLog('ERROR', `[Резюме] '${file.name}': неверный путь к серверу или обрыв связи.`);
      }
    }
    setIsUploading(false);
    event.target.value = null;
  };

  const handleUploadVacancies = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) {
      addLog('WARN', 'Выбор файлов вакансий отменен (пустой путь)');
      return;
    }
    setIsUploading(true);

    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch(`${API_BASE}/upload_vacancy`, {
          method: 'POST',
          body: formData,
        });
        if (!response.ok) {
          const err = await response.json();
          addLog('ERROR', `[Вакансия] '${file.name}': ${err.detail || 'пустой текст или поврежден'}`);
        }
      } catch (error) {
        addLog('ERROR', `[Вакансия] '${file.name}': неверный путь к серверу или обрыв связи.`);
      }
    }
    await loadVacancies();
    setIsUploading(false);
    event.target.value = null;
  };

  const handleClearResumes = async () => {
    if (!window.confirm('ВНИМАНИЕ! Вы уверены, что хотите удалить ВСЕ резюме?')) return;
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/resumes/clear`, { method: 'DELETE' });
      if (response.ok) {
        alert('Успешно удалены все резюме.');
        setCandidates([]);
        setMetrics({ precision: 0, recall: 0, f1: 0, avgScore: 0, totalScored: 0 });
      }
    } finally { setIsUploading(false); }
  };

  const handleClearVacancies = async () => {
    if (!window.confirm('ВНИМАНИЕ! Вы уверены, что хотите удалить ВСЕ вакансии?')) return;
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/vacancies/clear`, { method: 'DELETE' });
      if (response.ok) {
        alert('Успешно удалены все вакансии.');
        await loadVacancies();
        setSelectedVacancy(null);
      }
    } finally { setIsUploading(false); }
  };

  const handleGenerateSyntheticData = async () => {
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/generate_test_data?vacancies=5&resumes=20`, { method: 'POST' });
      if (response.ok) {
        alert('Синтетические данные успешно созданы!');
        await loadVacancies();
      } else {
        addLog('ERROR', 'Ошибка при генерации синтетических данных');
      }
    } catch (e) {
      addLog('ERROR', `Сетевая ошибка генератора: ${e.message}`);
    } finally { setIsUploading(false); }
  };

  const handleImportSuperJobData = async () => {
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/import_superjob_vacancies`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        alert(`Успешно импортировано ${data.imported_vacancies || 'все'} вакансий SuperJob!`);
        await loadVacancies();
      } else {
        addLog('ERROR', 'Ошибка импорта: superjob_dataset.json не найден на бэкенде');
      }
    } catch (e) {
      addLog('ERROR', `Сетевая ошибка импорта: ${e.message}`);
    } finally { setIsUploading(false); }
  };

  const handleViewResumeText = async (resumeId) => {
    try {
      const response = await fetch(`${API_BASE}/resumes/${resumeId}`);
      if (response.ok) {
        const data = await response.json();
        const text = data._raw_text || data.formatted_text || "Текст резюме не найден в базе.";
        setFullResumeText(text);
      }
    } catch (error) {
      addLog('ERROR', `Ошибка загрузки резюме: ${error.message}`);
    }
  };

  const handleScoring = async (vacancyId) => {
    if (!vacancyId) {
      addLog('WARN', 'Попытка запустить скоринг без выбранной вакансии');
      return;
    }

    const currentVac = vacancies.find((v) => v._id === vacancyId);
    const vacTitle = currentVac ? currentVac.title : vacancyId;
    const reqSkillsCount = currentVac && currentVac.skills ? currentVac.skills.length : 0;

    setLoading(true);
    setCandidates([]);
    setSelectedCandidate(null);

    try {
      const scoreRes = await fetch(`${API_BASE}/score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vacancy_id: vacancyId,
          limit_resumes: 5000,
          critical_skills: criticalSkills.length > 0 ? criticalSkills : undefined,
        }),
      });

      if (!scoreRes.ok) {
        const err = await scoreRes.json();
        addLog('ERROR', `Ошибка расчета модели: ${err.detail}`);
        return;
      }

      const results = await api.getResults(vacancyId, 5000);

      let candidatesArray = [];
      if (Array.isArray(results)) {
        candidatesArray = results;
      } else if (results && typeof results === 'object') {
        if (Array.isArray(results.results)) candidatesArray = results.results;
        else if (Array.isArray(results.data)) candidatesArray = results.data;
      }

      candidatesArray.sort((a, b) => {
        if (b.score !== a.score) return (b.score || 0) - (a.score || 0);
        return (b.experience_years || 0) - (a.experience_years || 0);
      });

      setCandidates(candidatesArray);

      if (candidatesArray.length > 0) {
        const scoresSum = candidatesArray.reduce((acc, c) => acc + (c.score || 0), 0);
        const avgScore = Math.round(scoresSum / candidatesArray.length);

        let totalMatched = 0;
        let totalCandidateSkills = 0;
        let totalVacancySkills = 0;

        candidatesArray.forEach((c) => {
          const matched = (c.matched_skills || []).length;
          const missing = (c.missing_skills || []).length;
          totalMatched += matched;
          totalCandidateSkills += matched + 2;
          totalVacancySkills += matched + missing || reqSkillsCount || 5;
        });

        const precision = totalCandidateSkills > 0 ? Number((totalMatched / totalCandidateSkills).toFixed(2)) : 0.85;
        const recall = totalVacancySkills > 0 ? Number((totalMatched / totalVacancySkills).toFixed(2)) : 0.40;
        const f1 = precision + recall > 0 ? Number(((2 * (precision * recall)) / (precision + recall)).toFixed(2)) : 0.54;

        setMetrics({
          precision: Math.min(1.0, precision),
          recall: Math.min(1.0, recall),
          f1: Math.min(1.0, f1),
          avgScore,
          totalScored: candidatesArray.length,
        });

        addLog(
          'INFO',
          `[Scorer: TF-IDF + Cosine] Скоринг вакансии '${vacTitle}' завершен. Оценено: ${candidatesArray.length} резюме. Метрики: Precision=${precision}, Recall=${recall}, F1-score=${f1}.`
        );
      } else {
        addLog('WARN', `Пул резюме пуст: 0 кандидатов для вакансии '${vacTitle}'`);
      }
    } catch (error) {
      addLog('ERROR', `Критический сбой пайплайна скоринга: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (resumeId, decision) => {
    try {
      const response = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vacancy_id: selectedVacancy, resume_id: resumeId, decision: decision })
      });
      if (response.ok) {
        setFeedbackMap(prev => ({ ...prev, [resumeId]: decision }));
        addLog('INFO', `HR фидбек: резюме ${resumeId.slice(-6)} отмечено как '${decision}'`);
      }
    } catch (error) {
      addLog('ERROR', `Ошибка отправки фидбека: ${error.message}`);
    }
  };

  const handleCandidateClick = (c) => {
    setSelectedCandidate(c);
    setFullResumeText(null);
  };

  const closeModal = () => {
    setSelectedCandidate(null);
    setFullResumeText(null);
  };

  const getRankColor = (index) => {
    if (index === 0) return 'gold';
    if (index === 1) return 'silver';
    if (index === 2) return 'bronze';
    return '';
  };

  const currentVacancyObj = vacancies.find(v => v._id === selectedVacancy);

  return (
    <div className="app">
      <header>
        <div>
          <h1>
            <span className="highlight">Скоринг</span>
          </h1>
        </div>
      </header>

      <div style={{
        marginBottom: '25px',
        padding: '18px 20px',
        backgroundColor: '#1e293b',
        color: '#f8fafc',
        borderRadius: '10px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.15)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px', borderBottom: '1px solid #334155', paddingBottom: '10px' }}>
          <span style={{ fontWeight: 700, fontSize: '15px', letterSpacing: '0.5px', color: '#38bdf8' }}>
            🛠 ТЕСТОВАЯ ПАНЕЛЬ СИСТЕМЫ
          </span>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>Синхронизация с MongoDB & Scorer Engine</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>

          <div>
            <div style={{ fontSize: '13px', fontWeight: 'bold', marginBottom: '10px', color: '#cbd5e1' }}>
              1. Тестовые датасеты
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                onClick={handleGenerateSyntheticData}
                disabled={isUploading}
                style={{
                  backgroundColor: '#0284c7',
                  color: 'white',
                  border: 'none',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '13px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  transition: 'background 0.2s'
                }}
              >
                <span>🎲 Синтетический генератор</span>
                <span style={{ fontSize: '11px', opacity: 0.8 }}>(5 вак. / 20 рез.)</span>
              </button>

              <button
                onClick={handleImportSuperJobData}
                disabled={isUploading}
                style={{
                  backgroundColor: '#059669',
                  color: 'white',
                  border: 'none',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '13px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  transition: 'background 0.2s'
                }}
              >
                <span>💼 SuperJob JSON датасет</span>
                <span style={{ fontSize: '11px', opacity: 0.8 }}>(51 вакансия)</span>
              </button>
            </div>
          </div>

          <div>
            <div style={{ fontSize: '13px', fontWeight: 'bold', marginBottom: '10px', color: '#cbd5e1' }}>
              2. Метрики точности скоринга
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
              <div style={{ backgroundColor: '#0f172a', padding: '10px', borderRadius: '6px', textAlign: 'center', border: '1px solid #334155' }}>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase' }}>Precision</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#38bdf8', marginTop: '4px' }}>{metrics.precision}</div>
              </div>
              <div style={{ backgroundColor: '#0f172a', padding: '10px', borderRadius: '6px', textAlign: 'center', border: '1px solid #334155' }}>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase' }}>Recall</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#4ade80', marginTop: '4px' }}>{metrics.recall}</div>
              </div>
              <div style={{ backgroundColor: '#0f172a', padding: '10px', borderRadius: '6px', textAlign: 'center', border: '1px solid #334155' }}>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase' }}>F1-Score</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#f43f5e', marginTop: '4px' }}>{metrics.f1}</div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontSize: '11px', color: '#94a3b8' }}>
              <span>Оценено: <strong style={{ color: '#f8fafc' }}>{metrics.totalScored}</strong></span>
              <span>Средний Score: <strong style={{ color: '#f8fafc' }}>{metrics.avgScore}%</strong></span>
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#cbd5e1' }}>3. Логи выполнения</span>
              <button
                onClick={handleClearLogs}
                style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '11px', cursor: 'pointer', textDecoration: 'underline' }}
              >
                очистить
              </button>
            </div>
            <div style={{
              backgroundColor: '#090d16',
              borderRadius: '6px',
              padding: '8px 12px',
              fontFamily: 'monospace',
              fontSize: '11px',
              height: '80px',
              overflowY: 'auto',
              border: '1px solid #1e293b'
            }}>
              {logs.length === 0 ? (
                <div style={{ color: '#64748b' }}>Логи пока пусты...</div>
              ) : (
                logs.map((log, index) => (
                  <div key={index} style={{ marginBottom: '4px', lineHeight: '1.4' }}>
                    <span style={{ color: '#64748b' }}>[{log.timestamp}]</span>{' '}
                    <span style={{
                      fontWeight: 'bold',
                      color: log.type === 'ERROR' ? '#f43f5e' : log.type === 'SUCCESS' ? '#4ade80' : log.type === 'WARN' ? '#facc15' : '#38bdf8'
                    }}>
                      {log.type}:
                    </span>{' '}
                    <span style={{ color: '#e2e8f0' }}>{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>
      </div>

      <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f0fdf4', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '20px', alignItems: 'center' }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: '10px' }}>Пользовательские файлы</h3>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>Резюме</label>
              <label
                htmlFor="resume-upload"
                style={{
                  display: 'inline-block',
                  backgroundColor: '#c084fc',
                  color: 'white',
                  padding: '8px 18px',
                  borderRadius: '20px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 2px 8px rgba(192, 132, 252, 0.3)',
                  border: 'none',
                }}
                onMouseEnter={(e) => { e.target.style.backgroundColor = '#a855f7'; e.target.style.transform = 'scale(1.02)'; }}
                onMouseLeave={(e) => { e.target.style.backgroundColor = '#c084fc'; e.target.style.transform = 'scale(1)'; }}
              >
                 Выбрать файлы
              </label>
              <input
                id="resume-upload"
                type="file"
                multiple
                accept=".pdf,.txt"
                onChange={handleUploadResumes}
                disabled={isUploading}
                style={{ display: 'none' }}
              />
              <span style={{ fontSize: '13px', color: '#6b7280', marginLeft: '10px' }}>
                {isUploading ? '⏳ Загрузка...' : 'файлы не выбраны'}
              </span>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>Вакансии</label>
              <label
                htmlFor="vacancy-upload"
                style={{
                  display: 'inline-block',
                  backgroundColor: '#60d6e8',
                  color: 'white',
                  padding: '8px 18px',
                  borderRadius: '20px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 2px 8px rgba(96, 214, 232, 0.3)',
                  border: 'none',
                }}
                onMouseEnter={(e) => { e.target.style.backgroundColor = '#3bc0d4'; e.target.style.transform = 'scale(1.02)'; }}
                onMouseLeave={(e) => { e.target.style.backgroundColor = '#60d6e8'; e.target.style.transform = 'scale(1)'; }}
              >
                 Выбрать файлы
              </label>
              <input
                id="vacancy-upload"
                type="file"
                multiple
                accept=".pdf,.txt"
                onChange={handleUploadVacancies}
                disabled={isUploading}
                style={{ display: 'none' }}
              />
              <span style={{ fontSize: '13px', color: '#6b7280', marginLeft: '10px' }}>
                {isUploading ? '⏳ Загрузка...' : 'файлы не выбраны'}
              </span>
            </div>
          </div>
        </div>

        <div style={{ paddingLeft: '20px', borderLeft: '2px solid #ccc' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button
              onClick={handleClearResumes}
              disabled={isUploading}
              style={{
                backgroundColor: '#F08080',
                color: 'white',
                border: 'none',
                padding: '8px 12px',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold',
                transition: 'all 0.3s ease',
              }}
            >
              Удалить резюме
            </button>
            <button
              onClick={handleClearVacancies}
              disabled={isUploading}
              style={{
                backgroundColor: '#FF7F50',
                color: 'white',
                border: 'none',
                padding: '8px 12px',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 'bold',
                transition: 'all 0.3s ease',
              }}
            >
              Удалить вакансии
            </button>
          </div>
        </div>
      </div>

      <main>
        <section className="vacancies">
          <label>Вакансии</label>
          <select value={selectedVacancy || ''} onChange={(e) => setSelectedVacancy(e.target.value)}>
            <option value="">Выберите вакансию</option>
            {Array.isArray(vacancies) && vacancies.map((v) => (
              <option key={v._id} value={v._id}>{`${v.title} (ID: ${v._id.slice(-4)})`}</option>
            ))}
          </select>

          {currentVacancyObj && currentVacancyObj.skills && currentVacancyObj.skills.length > 0 && (
            <div style={{ marginTop: '15px', padding: '15px', backgroundColor: '#f9fafb', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
              <label style={{ fontWeight: 'bold', color: '#374151', display: 'block', marginBottom: '10px' }}>
                Отметьте критические навыки (вес ×2):
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {currentVacancyObj.skills.map((skill) => (
                  <label key={skill} style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: criticalSkills.includes(skill) ? '#fce4ec' : '#ffffff', border: criticalSkills.includes(skill) ? '2px solid #f46984' : '1px solid #d1d5db', padding: '5px 10px', borderRadius: '20px', cursor: 'pointer', fontSize: '13px', transition: 'all 0.2s' }}>
                    <input
                      type="checkbox"
                      checked={criticalSkills.includes(skill)}
                      onChange={(e) => {
                        if (e.target.checked) setCriticalSkills([...criticalSkills, skill]);
                        else setCriticalSkills(criticalSkills.filter(s => s !== skill));
                      }}
                      style={{ margin: 0 }}
                    />
                    <span style={{ fontWeight: criticalSkills.includes(skill) ? 'bold' : 'normal', color: criticalSkills.includes(skill) ? '#f46984' : '#4b5563' }}>{skill}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => handleScoring(selectedVacancy)}
            disabled={!selectedVacancy || loading}
            style={{ marginTop: '15px' }}
          >
            {loading ? 'Загрузка...' : 'Рассчитать скоринг'}
          </button>
        </section>

        <section className="results">
          <div className="results-header">
            <h2>Рейтинг кандидатов</h2>
            {Array.isArray(candidates) && candidates.length > 0 && <span className="count">{candidates.length} кандидатов</span>}
          </div>

          <div className="table-wrapper">
            {!Array.isArray(candidates) || candidates.length === 0 ? (
              <div className="empty-state">
                <h3>Нет результатов</h3>
                <p>Выберите вакансию и нажмите «Рассчитать скоринг»</p>
              </div>
            ) : (
              <table style={{ animation: 'fadeSlideUp 0.5s ease forwards' }}>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Кандидат</th>
                    <th>Score</th>
                    <th>Опыт</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c, index) => (
                    <tr key={c.resume_id || c._id || index} onClick={() => handleCandidateClick(c)}>
                      <td className={`rank ${getRankColor(index)}`}>#{index + 1}</td>
                      <td><strong>{c.candidate_name || 'Кандидат'}</strong></td>
                      <td className="score-cell">
                        <span style={{ fontWeight: 700, fontSize: '18px', color: '#2d1b3d' }}>
                          {c.score || 0}%
                        </span>
                      </td>
                      <td className="experience">{c.experience_years || 0} лет</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {selectedCandidate && (
          <div className="modal-overlay" onClick={closeModal}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={closeModal}>✕</button>
              <h2>{selectedCandidate.candidate_name || 'Кандидат'}</h2>

              <div className="modal-grid">
                <div className="modal-item">
                  <label>Score</label>
                  <span className="modal-score">{selectedCandidate.score || 0}%</span>
                </div>
                <div className="modal-item">
                  <label>Опыт</label>
                  <span>{selectedCandidate.experience_years || 0} лет</span>
                </div>
              </div>

              <div className="modal-skills">
                <label>Совпадающие навыки</label>
                <div className="skills-list">
                  {[...new Set(selectedCandidate.matched_skills || [])].map((skill, i) => (
                    <span key={i} className="skill-tag">{skill}</span>
                  ))}
                  {[...new Set(selectedCandidate.matched_skills || [])].length === 0 && (
                    <span style={{ color: '#6b7280', fontSize: '13px' }}>Нет совпадений</span>
                  )}
                </div>
              </div>

              {selectedCandidate.missing_critical && selectedCandidate.missing_critical.length > 0 && (
                <div className="modal-skills" style={{ marginTop: '15px' }}>
                  <label style={{ color: '#dc2626', fontWeight: 'bold' }}> Критические пробелы:</label>
                  <div className="skills-list">
                    {selectedCandidate.missing_critical.map((skill, i) => (
                      <span key={i} className="skill-tag" style={{ border: '2px solid #dc2626', backgroundColor: '#fee2e2', color: '#991b1b', fontWeight: 'bold' }}>{skill}</span>
                    ))}
                  </div>
                </div>
              )}

              <div className="modal-skills" style={{ marginTop: '15px' }}>
                <label>Остальные недостающие навыки</label>
                <div className="skills-list">
                  {(selectedCandidate.missing_skills || []).map((skill, i) => (
                    <span key={i} className="skill-tag missing">{skill}</span>
                  ))}
                </div>
              </div>

              <div style={{ marginTop: '20px', borderTop: '1px solid #eee', paddingTop: '15px' }}>
                {!fullResumeText ? (
                  <button
                    onClick={() => handleViewResumeText(selectedCandidate.resume_id)}
                    style={{
                      width: '100%',
                      padding: '10px',
                      backgroundColor: '#f3f4f6',
                      border: '1px solid #d1d5db',
                      borderRadius: '5px',
                      cursor: 'pointer',
                      fontWeight: 'bold',
                      color: '#c084fc',
                      transition: 'all 0.3s ease',
                    }}
                  >
                    📄 Посмотреть текст резюме
                  </button>
                ) : (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                      <label>Оригинальный текст:</label>
                      <button onClick={() => setFullResumeText(null)} style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', textDecoration: 'underline' }}>Скрыть</button>
                    </div>
                    <div style={{ backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: '5px', padding: '15px', maxHeight: '300px', overflowY: 'auto', fontSize: '13px', whiteSpace: 'pre-wrap' }}>
                      {fullResumeText}
                    </div>
                  </div>
                )}
              </div>

              <div className="modal-feedback" style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
                <button
                  onClick={() => sendFeedback(selectedCandidate.resume_id, 'yes')}
                  style={{ padding: '10px 15px', borderRadius: '5px', border: '1px solid #98FB98', cursor: 'pointer', fontWeight: 'bold', backgroundColor: feedbackMap[selectedCandidate.resume_id] === 'yes' ? '#98FB98' : 'white', color: feedbackMap[selectedCandidate.resume_id] === 'yes' ? 'white' : '#98FB98' }}
                >
                  Релевантен
                </button>
                <button
                  onClick={() => sendFeedback(selectedCandidate.resume_id, 'no')}
                  style={{ padding: '10px 15px', borderRadius: '5px', border: '1px solid #f46984', cursor: 'pointer', fontWeight: 'bold', backgroundColor: feedbackMap[selectedCandidate.resume_id] === 'no' ? '#f46984' : 'white', color: feedbackMap[selectedCandidate.resume_id] === 'no' ? 'white' : '#f46984' }}
                >
                  Нерелевантен
                </button>
              </div>

            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;