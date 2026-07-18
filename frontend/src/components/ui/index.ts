export * from "./Badge";
export * from "./Button";
export * from "./Card";
export * from "./Input";
export * from "./Page";
export { EmptyState } from "../UI";

/** Une classes condicionais sem introduzir dependência entre os dois barrels de UI. */
export const cn = (...classes: Array<string | false | null | undefined>) =>
  classes.filter(Boolean).join(" ");
