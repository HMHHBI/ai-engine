export { act } from "react";
export default { act: (...args: any[]) => (require("react").act || ((cb: any) => cb()))(...args) };
