const API_URL = 'http://localhost:8000';

export const api = {
  getVacancies: async () => {
    try {
      const response = await fetch(`${API_URL}/vacancies`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Ошибка в getVacancies:', error);
      return [];
    }
  },

  getResults: async (vacancyId, limit = 5000) => {
    try {
      const response = await fetch(`${API_URL}/results/${vacancyId}?top=${limit}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Ошибка в getResults:', error);
      return [];
    }
  },
};
