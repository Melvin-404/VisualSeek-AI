FROM node:20-alpine
WORKDIR /app
RUN npm install -g pnpm@11.3.0
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/
COPY packages/shared-types/package.json ./packages/shared-types/
RUN pnpm install --frozen-lockfile
COPY apps/web ./apps/web
COPY packages/shared-types ./packages/shared-types
EXPOSE 3000
CMD ["pnpm", "--filter", "web", "dev"]
