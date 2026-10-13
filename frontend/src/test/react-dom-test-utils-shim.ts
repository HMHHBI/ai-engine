/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-require-imports */
export { act } from "react";
const shim = { act: (...args: any[]) => (require("react").act || ((cb: any) => cb()))(...args) };
export default shim;
