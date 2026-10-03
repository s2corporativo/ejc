import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { ThemeProvider } from "@/components/theme-provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "JuridIA — Inteligência Artificial para o Direito Brasileiro",
  description:
    "De petições a sentenças, a IA que mais entende — e mais produz — para o Direito brasileiro. Anonimização local (tarja-1), conformidade LGPD e Resolução CNJ 615/2025.",
  keywords: [
    "IA jurídica",
    "minuta",
    "petição",
    "sentença",
    "Direito brasileiro",
    "LGPD",
    "CNJ 615/2025",
    "jurisprudência",
  ],
  authors: [{ name: "JuridIA" }],
  icons: {
    icon: "https://z-cdn.chatglm.cn/z-ai/static/logo.svg",
  },
  openGraph: {
    title: "JuridIA — IA para o Direito Brasileiro",
    description:
      "Plataforma de IA para geração de minutas jurídicas com anonimização local e conformidade LGPD.",
    siteName: "JuridIA",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground min-h-screen flex flex-col`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          {children}
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
