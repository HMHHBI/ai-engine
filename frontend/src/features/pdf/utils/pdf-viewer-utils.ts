export const MIN_PAGE = 1;
export const MIN_SCALE = 0.5;
export const MAX_SCALE = 3;
export const SCALE_STEP = 0.25;

export function clampPage(page: number, numPages: number): number {
  if (numPages <= 0) {
    return MIN_PAGE;
  }

  return Math.min(Math.max(page, MIN_PAGE), numPages);
}
