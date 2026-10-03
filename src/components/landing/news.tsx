"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Calendar } from "lucide-react";
import type { NewsDTO } from "@/lib/types";

const CATEGORY_LABEL: Record<string, string> = {
  recurso: "Novo recurso",
  novoproduto: "Novo produto",
  recado: "Recado",
  parceria: "Parceria",
};

export function News() {
  const [items, setItems] = useState<NewsDTO[]>([]);
  useEffect(() => {
    fetch("/api/news")
      .then((r) => r.json())
      .then((d) => setItems(d.news || []))
      .catch(() => null);
  }, []);

  return (
    <section id="novidades" className="border-b border-border">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-wider text-primary">
            Novidades
          </span>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            Os últimos recursos e melhorias do JuridIA
          </h2>
        </div>

        <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {items.length === 0 && (
            <>
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-56 animate-pulse rounded-xl border border-border bg-secondary/40"
                />
              ))}
            </>
          )}
          {items.slice(0, 6).map((n, i) => (
            <motion.article
              key={n.id}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.05 }}
              className="group flex flex-col rounded-xl border border-border bg-card p-5 transition-shadow hover:shadow-md"
            >
              <div className="mb-3 flex items-center justify-between text-xs">
                <span className="rounded-full bg-secondary px-2.5 py-1 font-medium text-secondary-foreground">
                  {CATEGORY_LABEL[n.category] || n.category}
                </span>
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Calendar className="h-3 w-3" />
                  {new Date(n.date).toLocaleDateString("pt-BR", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
              </div>
              <h3 className="text-lg font-semibold leading-tight">{n.title}</h3>
              <p className="mt-2 flex-1 text-sm text-muted-foreground">
                {n.summary}
              </p>
              <button className="mt-4 flex items-center gap-1 text-sm font-medium text-primary opacity-80 transition-opacity group-hover:opacity-100">
                Ler artigo
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
