/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars */
import "@testing-library/jest-dom/vitest";
import * as React from "react";
import { vi } from "vitest";

// 1. Force test environment
(process.env as any).NODE_ENV = "test";
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

// 2. Direct React 19 act shim for react-dom/test-utils
const actShim = (cb: () => any) => {
  return cb();
};

vi.mock("react-dom/test-utils", () => ({
  act: actShim,
  default: { act: actShim },
}));

// 3. Ensure globalThis.act is accessible
(globalThis as any).act = actShim;
