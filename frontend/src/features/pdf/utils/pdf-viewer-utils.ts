export const MIN_PAGE = 1;

export const MIN_SCALE = 0.5;
export const MAX_SCALE = 3;
export const SCALE_STEP = 0.25;
export const DEFAULT_SCALE = 1;

export function clampPage(page: number, numPages: number): number {
  if (numPages <= 0) {
    return MIN_PAGE;
  }

  return Math.min(Math.max(page, MIN_PAGE), numPages);
}

export function clampScale(scale: number): number {
  return Math.min(Math.max(scale, MIN_SCALE), MAX_SCALE);
}

export function zoomIn(scale: number): number {
  return clampScale(
    Number((scale + SCALE_STEP).toFixed(2)),
  );
}

export function zoomOut(scale: number): number {
  return clampScale(
    Number((scale - SCALE_STEP).toFixed(2)),
  );
}

export function resetZoom(): number {
  return DEFAULT_SCALE;
}

export function calculateFitScale(
  pageWidth: number,
  pageHeight: number,
  containerWidth: number,
  containerHeight: number,
): number {
  if (
    pageWidth <= 0 ||
    pageHeight <= 0 ||
    containerWidth <= 0 ||
    containerHeight <= 0
  ) {
    return DEFAULT_SCALE;
  }

  const widthScale = containerWidth / pageWidth;
  const heightScale = containerHeight / pageHeight;

  return clampScale(Math.min(widthScale, heightScale));
}

export function calculateFitWidthScale(
  pageWidth: number,
  containerWidth: number,
): number {
  if (pageWidth <= 0 || containerWidth <= 0) {
    return DEFAULT_SCALE;
  }

  return clampScale(containerWidth / pageWidth);
}

export function calculateFitHeightScale(
  pageHeight: number,
  containerHeight: number,
): number {
  if (pageHeight <= 0 || containerHeight <= 0) {
    return DEFAULT_SCALE;
  }

  return clampScale(containerHeight / pageHeight);
}
