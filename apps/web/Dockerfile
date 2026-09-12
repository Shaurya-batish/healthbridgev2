# Build context MUST be the repo root (not apps/web), because sync-rules.mjs
# needs rules/imnci-rules.v1.json from outside this directory. Example:
#   docker build -f apps/web/Dockerfile -t healthbridge-web .
# infra/docker-compose.yml wires this up with `context: ..` / `dockerfile: apps/web/Dockerfile`.
FROM node:20-alpine AS base
WORKDIR /app

FROM base AS deps
COPY apps/web/package.json apps/web/package-lock.json* ./apps/web/
RUN cd apps/web && npm install --no-audit --no-fund

FROM base AS builder
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY rules ./rules
COPY apps/web ./apps/web
RUN cd apps/web && npm run build

FROM base AS runner
ENV NODE_ENV=production
WORKDIR /app/apps/web
COPY --from=builder /app/apps/web/public ./public
COPY --from=builder /app/apps/web/.next ./.next
COPY --from=builder /app/apps/web/node_modules ./node_modules
COPY --from=builder /app/apps/web/package.json ./package.json
EXPOSE 3000
CMD ["npm", "run", "start"]
