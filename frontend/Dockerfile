FROM node:24-bookworm AS node_source

FROM debian:bookworm-slim AS base
COPY --from=node_source /usr/local /usr/local
ENV PATH="/usr/local/bin:${PATH}"
WORKDIR /workspace

# Local dev target (default for the base docker-compose.yml): bind-mounted
# source, hot reload via `next dev`.
FROM base AS dev
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0"]

FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm ci

FROM deps AS build
COPY . .
RUN npm run build

# Production target: standalone Next.js server output only, no source bind
# mount, no dev tooling — this is what docker-compose.prod.yml builds.
FROM base AS prod
ENV NODE_ENV=production
# Docker sets HOSTNAME=<container-id> automatically, which the standalone
# server misreads as the bind address (causing a DNS lookup on startup that
# fails and crash-loops the container) unless overridden here.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
COPY --from=build /workspace/public ./public
COPY --from=build /workspace/.next/standalone ./
COPY --from=build /workspace/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
