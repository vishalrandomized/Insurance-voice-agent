import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AssureLine | Document-grounded insurance guidance",
  description:
    "A realtime insurance product advisor grounded in policy documents.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
