# ── EJC Frontend — build Vite + Nginx estático ────────────
FROM node:22.22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
# npm ci falha ruidosamente se o lockfile divergir (sem fallback silencioso p/ npm install).
RUN npm ci
COPY . .
# Flag do menu de 9 módulos (Onda 1): o default ATIVO vive no código
# (canonicalNavigation.ts). Rollback global de infra: build com
# VITE_EJC_MENU_9=false (build arg do compose / .env do host) — sem tocar código.
# O compose injeta o valor do .env do host; .dockerignore barra .env do
# contexto, então o ARG/ENV é o único caminho válido até o Vite.
ARG VITE_EJC_MENU_9
ENV VITE_EJC_MENU_9=$VITE_EJC_MENU_9
# Flags das abas das ondas 3/4 (config/w3Tabs.ts): rollback global idêntico —
# VITE_EJC_W4_TABS=false desliga Tarefas e Intimações no workspace do caso.
ARG VITE_EJC_W4_TABS
ENV VITE_EJC_W4_TABS=$VITE_EJC_W4_TABS
RUN sed -i "s/ejc-v3/ejc-v3-$(date +%s)/" public/sw.js
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
