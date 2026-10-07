import { render, screen } from '@testing-library/react';
import App from './App';

test('renders scoring app title', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /скоринг/i })).toBeInTheDocument();
});
