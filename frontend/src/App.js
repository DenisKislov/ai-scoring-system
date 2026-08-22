import React, { useState, useEffect } from 'react';
import { api } from './api/api';
import './App.css';

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

  useEffect(() => {
    const loadVacancies = async () => {
      try {
        const data = await api.getVacancies();
        if (Array.isArray(data)) {
          setVacancies(data);
        } else {
          setVacancies([]);
        }
      } catch (error) {
        console.error('Ошибка загрузки вакансий:', error);
        setVacancies([]);
      }
    };
    loadVacancies();
  }, []);

  useEffect(() => {
    setCriticalSkills([]);
  }, [selectedVacancy]);

  const handleUploadResumes = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;
    setIsUploading(true);
    let successCount = 0;
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch('http://127.0.0.1:8000/upload_resume', {
          method: 'POST',
          body: formData,
        });
        if (response.ok) successCount++;
      } catch (error) {
        console.error(`Ошибка сети при загрузке ${file.name}:`, error);
      }
    }
    alert(`Успешно добавлено резюме: ${successCount} из ${files.length}.`);
    setIsUploading(false);
    event.target.value = null;
  };

  const handleUploadVacancies = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;
    setIsUploading(true);
    let successCount = 0;
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch('http://127.0.0.1:8000/upload_vacancy', {
          method: 'POST',
          body: formData,
        });
        if (response.ok) successCount++;
      } catch (error) {
        console.error(`Ошибка сети при загрузке ${file.name}:`, error);
      }
    }
    alert(`Успешно добавлено вакансий: ${successCount} из ${files.length}. Обновите страницу.`);
    setIsUploading(false);
    event.target.value = null;
  };

  const handleClearResumes = async () => {
    if (!window.confirm('ВНИМАНИЕ! Вы уверены, что хотите удалить ВСЕ резюме?')) return;
    setIsUploading(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/resumes/clear', { method: 'DELETE' });
      if (response.ok) {
        const data = await response.json();
        alert(`Успешно удалено резюме: ${data.deleted_count}`);
        setCandidates([]);
      }
    } finally { setIsUploading(false); }
  };

  const handleClearVacancies = async () => {
    if (!window.confirm('ВНИМАНИЕ! Вы уверены, что хотите удалить ВСЕ вакансии?')) return;
    setIsUploading(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/vacancies/clear', { method: 'DELETE' });
      if (response.ok) {
        const data = await response.json();
        alert(`Успешно удалено вакансий: ${data.deleted_count}. Обновите страницу.`);
      }
    } finally { setIsUploading(false); }
  };

  const handleGenerateData = async () => {
    setIsUploading(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/generate_test_data?vacancies=5&resumes=20', { method: 'POST' });
      if (response.ok) alert('Тестовые данные успешно сгенерированы! Обновите страницу.');
    } finally { setIsUploading(false); }
  };

  const handleViewResumeText = async (resumeId) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/resumes/${resumeId}`);
      if (response.ok) {
        const data = await response.json();
        const text = data._raw_text || data.formatted_text || "Текст резюме не найден в базе.";
        setFullResumeText(text);
      } else {
        alert('Не удалось загрузить данные резюме с сервера.');
      }
    } catch (error) {
      console.error('Ошибка загрузки резюме:', error);
    }
  };

  const handleScoring = async (vacancyId) => {
    if (!vacancyId) return;

    setLoading(true);
    setCandidates([]);
    setSelectedCandidate(null);

    try {
      await fetch('http://127.0.0.1:8000/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vacancy_id: vacancyId,
          limit_resumes: 5000,
          critical_skills: criticalSkills.length > 0 ? criticalSkills : undefined
        })
      });

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
      if (candidatesArray.length === 0) alert('Нет результатов для этой вакансии');
    } catch (error) {
      console.error('Ошибка при скоринге:', error);
      alert('Не удалось выполнить скоринг. Проверьте, что бэкенд запущен.');
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (resumeId, decision) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vacancy_id: selectedVacancy, resume_id: resumeId, decision: decision })
      });
      if (response.ok) {
        setFeedbackMap(prev => ({ ...prev, [resumeId]: decision }));
      }
    } catch (error) {
      console.error('Ошибка фидбека:', error);
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

  const getScoreColor = (score) => {
    if (score >= 70) return 'high';
    if (score >= 40) return 'medium';
    return 'low';
  };

  const currentVacancyObj = vacancies.find(v => v._id === selectedVacancy);

  return (
    <div className="app">
      <header>
        <h1><span className="highlight">Скоринг</span></h1>
      </header>

      <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f0fdf4', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '20px' }}>
        <div>
          <h3 style={{ marginTop: 0 }}>Загрузка данных</h3>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>Резюме</label>
              <input type="file" multiple accept=".pdf,.txt" onChange={handleUploadResumes} disabled={isUploading} style={{ maxWidth: '280px' }}/>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>Вакансии</label>
              <input type="file" multiple accept=".pdf,.txt" onChange={handleUploadVacancies} disabled={isUploading} style={{ maxWidth: '280px' }}/>
            </div>
          </div>
        </div>

        <div style={{ paddingLeft: '20px', borderLeft: '2px solid #ccc' }}>
          <button onClick={handleGenerateData} disabled={isUploading} style={{ backgroundColor: '#0ea5e9', color: 'white', border: 'none', padding: '10px 15px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', width: '100%' }}>
            🧪 Сгенерировать данные
          </button>
          <div style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>(5 вакансий, 20 резюме)</div>
        </div>

        <div style={{ paddingLeft: '20px', borderLeft: '2px solid #ccc' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button onClick={handleClearResumes} disabled={isUploading} style={{ backgroundColor: '#ef4444', color: 'white', border: 'none', padding: '8px 12px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>🗑 Удалить резюме</button>
            <button onClick={handleClearVacancies} disabled={isUploading} style={{ backgroundColor: '#ef4444', color: 'white', border: 'none', padding: '8px 12px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>🗑 Удалить вакансии</button>
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
                  <label key={skill} style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: criticalSkills.includes(skill) ? '#fee2e2' : '#ffffff', border: criticalSkills.includes(skill) ? '1px solid #ef4444' : '1px solid #d1d5db', padding: '5px 10px', borderRadius: '20px', cursor: 'pointer', fontSize: '13px', transition: 'all 0.2s' }}>
                    <input
                      type="checkbox"
                      checked={criticalSkills.includes(skill)}
                      onChange={(e) => {
                        if (e.target.checked) setCriticalSkills([...criticalSkills, skill]);
                        else setCriticalSkills(criticalSkills.filter(s => s !== skill));
                      }}
                      style={{ margin: 0 }}
                    />
                    <span style={{ fontWeight: criticalSkills.includes(skill) ? 'bold' : 'normal', color: criticalSkills.includes(skill) ? '#b91c1c' : '#4b5563' }}>{skill}</span>
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
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Кандидат</th>
                    <th>Score</th>
                    <th>Опыт</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c, index) => {
                    return (
                      <tr key={c.resume_id || c._id || index} onClick={() => handleCandidateClick(c)}>
                        <td className={`rank ${getRankColor(index)}`}>#{index + 1}</td>
                        <td><strong>{c.candidate_name || 'Кандидат'}</strong></td>
                        <td className="score-cell">
                          <div className="score-bar-wrapper">
                            <span>{c.score || 0}%</span>
                            <div className="score-bar">
                              <div className={`score-bar-fill ${getScoreColor(c.score || 0)}`} style={{ width: `${c.score || 0}%` }}></div>
                            </div>
                          </div>
                        </td>
                        <td className="experience">{c.experience_years || 0} лет</td>
                      </tr>
                    );
                  })}
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
                  <button onClick={() => handleViewResumeText(selectedCandidate.resume_id)} style={{ width: '100%', padding: '10px', backgroundColor: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: '5px', cursor: 'pointer', fontWeight: 'bold' }}>
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
                  style={{ padding: '10px 15px', borderRadius: '5px', border: '1px solid #16a34a', cursor: 'pointer', fontWeight: 'bold', backgroundColor: feedbackMap[selectedCandidate.resume_id] === 'yes' ? '#16a34a' : 'white', color: feedbackMap[selectedCandidate.resume_id] === 'yes' ? 'white' : '#16a34a' }}
                >
                  Релевантен
                </button>
                <button
                  onClick={() => sendFeedback(selectedCandidate.resume_id, 'no')}
                  style={{ padding: '10px 15px', borderRadius: '5px', border: '1px solid #dc2626', cursor: 'pointer', fontWeight: 'bold', backgroundColor: feedbackMap[selectedCandidate.resume_id] === 'no' ? '#dc2626' : 'white', color: feedbackMap[selectedCandidate.resume_id] === 'no' ? 'white' : '#dc2626' }}
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