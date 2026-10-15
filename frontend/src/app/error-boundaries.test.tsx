import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorBoundary from './error';
import GlobalError from './global-error';

describe('App Router Error Boundaries', () => {
  it('renders route-level ErrorBoundary and triggers reset on retry click', () => {
    const resetMock = vi.fn();
    const testError = new Error('Test route failure');

    render(<ErrorBoundary error={testError} reset={resetMock} />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText(/An unexpected error occurred/i)).toBeInTheDocument();

    const retryButton = screen.getByRole('button', { name: /try again/i });
    fireEvent.click(retryButton);

    expect(resetMock).toHaveBeenCalledTimes(1);
  });

  it('renders GlobalError root boundary and triggers reset on reload click', () => {
    const resetMock = vi.fn();
    const testError = new Error('Critical root failure');

    render(<GlobalError error={testError} reset={resetMock} />);

    expect(screen.getByText('Critical Application Error')).toBeInTheDocument();

    const reloadButton = screen.getByRole('button', { name: /reload application/i });
    fireEvent.click(reloadButton);

    expect(resetMock).toHaveBeenCalledTimes(1);
  });
});
