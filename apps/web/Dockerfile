# ============================================
# Vision Query Web - Dockerfile
# ============================================
FROM node:22-alpine AS base

# Install pnpm
RUN npm install -g pnpm@11.3.0

WORKDIR /app

# Copy workspace root config
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./

# Copy all workspace package.json files
COPY apps/web/package.json ./apps/web/
COPY packages/shared-types/package.json ./packages/shared-types/
COPY packages/ui/package.json ./packages/ui/

# Copy workspace packages source
COPY packages/shared-types ./packages/shared-types
COPY packages/ui ./packages/ui

# Copy web app source
COPY apps/web ./apps/web

# Install dependencies after copying source so pnpm workspace linking works perfectly
RUN pnpm install --frozen-lockfile

# Set API URL for the frontend
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_APP_ENV=development

EXPOSE 3000

# Run Next.js dev server from root using pnpm filter
CMD ["pnpm", "--filter", "web", "dev", "--hostname", "0.0.0.0"]
