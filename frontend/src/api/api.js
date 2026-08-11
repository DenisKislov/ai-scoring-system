// frontend/src/api/api.js
const API_URL = 'http://127.0.0.1:8000';

export const api = {
  // Получить список вакансий
  async getVacancies(limit = 10) {
    const response = await fetch(`${API_URL}/vacancies?limit=${limit}`);
    return response.json();
  },

  // Запустить скоринг для вакансии
  async runScoring(vacancyId, limitResumes = 10000) {
    const response = await fetch(`${API_URL}/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vacancy_id: vacancyId, limit_resumes: limitResumes })
    });
    return response.json();
  },

  // Получить результаты скоринга
  async getResults(vacancyId, top = 10) {
    const response = await fetch(`${API_URL}/results/${vacancyId}?top=${top}`);
    return response.json();
  },

  // Получить резюме с подсветкой
  async getResume(resumeId) {
    const response = await fetch(`${API_URL}/resumes/${resumeId}`);
    return response.json();
  }
};