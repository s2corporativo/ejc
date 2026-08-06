# ── EJC Frontend — build Vite + Nginx estático ────────────
FROM node:22.22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
# npm ci falha ruidosamente se o lockfile divergir (sem fallback silencioso p/ npm install).
RUN npm ci
COPY . .
RUN sed -i "s/ejc-v3/ejc-v3-$(date +%s)/" public/sw.js
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
