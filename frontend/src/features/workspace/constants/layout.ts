/**
 * Workspace Layout Boundary Contracts (M4)
 * Enforces dual-pane constraints so neither pane becomes unusably constrained.
 */

// Minimum usable width for the document pane (pixels)
export const WORKSPACE_DOCUMENT_MIN_WIDTH = 360;

// Maximum width ratio for the document pane relative to the container width (60vw / 0.60)
export const WORKSPACE_DOCUMENT_MAX_RATIO = 0.60;

// Default initial width ratio for the document pane (45% / 0.45)
export const WORKSPACE_DOCUMENT_DEFAULT_RATIO = 0.45;

// Absolute minimum usable width for the chat pane to preserve message readability & composer usability (pixels)
export const WORKSPACE_CHAT_MIN_WIDTH = 420;
