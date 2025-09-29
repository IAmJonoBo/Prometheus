import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Prometheus Strategy OS",
  description: "Evidence-linked decision automation",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
