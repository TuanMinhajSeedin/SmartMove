import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartMove — Agentic transport assistant",
  description:
    "Multilingual LangGraph human-in-the-loop chatbot for transport planning in Sri Lanka.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
