declare module "react" {
  export type ReactNode = any;
}

declare module "*.css";
declare module "next/link" {
  const Link: any;
  export default Link;
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
}
