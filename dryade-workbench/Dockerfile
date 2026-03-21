# Context: repo root (build context set in docker-compose.yml)
# Vite + React SPA — builds to /dist, served by nginx
FROM node:20-alpine AS deps
WORKDIR /build/dryade-workbench
COPY dryade-workbench/package.json dryade-workbench/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /build
ARG VITE_API_BASE_URL=http://localhost:8080
ARG VITE_DRYADE_PUBLIC_KEY=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_DRYADE_PUBLIC_KEY=$VITE_DRYADE_PUBLIC_KEY
# Copy plugin-sdk CSS (needed by PluginSandbox.tsx ?raw imports via ../../../packages/)
COPY packages/plugin-sdk/src/styles/ ./packages/plugin-sdk/src/styles/
# Copy workbench source and dependencies
COPY dryade-workbench/ ./dryade-workbench/
COPY --from=deps /build/dryade-workbench/node_modules ./dryade-workbench/node_modules
WORKDIR /build/dryade-workbench
RUN npm run build

FROM nginx:alpine AS runner
COPY --from=builder /build/dryade-workbench/dist /usr/share/nginx/html
# SPA fallback + API reverse proxy to backend
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    location /api/ {\n\
        proxy_pass http://dryade:8080;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $scheme;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_read_timeout 300s;\n\
    }\n\
    location /ws/ {\n\
        proxy_pass http://dryade:8080;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_read_timeout 86400s;\n\
    }\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
