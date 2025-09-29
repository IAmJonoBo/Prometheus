export {};

declare module "*.css";

declare module "next/link" {
  const Link: any;
  export default Link;
}

declare global {
  namespace React {
    // Relax ReactNode usage while JSX clean-up is in progress.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    type ReactNode = any;
  }

  namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}
