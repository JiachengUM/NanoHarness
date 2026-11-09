FROM node:22-alpine

WORKDIR /app

RUN npm install -g pnpm@11.5.1

COPY pnpm-workspace.yaml .
COPY pnpm-lock.yaml .
COPY package.json .
COPY tsconfig.base.json .
COPY tsconfig.json .
COPY tsconfig.build.json .
COPY turbo.json .

COPY packages/shared/package.json packages/shared/
COPY packages/database/package.json packages/database/
COPY packages/llm/package.json packages/llm/
COPY packages/makedata/package.json packages/makedata/

COPY apps/backend/package.json apps/backend/

RUN pnpm install --frozen-lockfile

COPY packages/shared/src packages/shared/src
COPY packages/shared/tsconfig.json packages/shared/
COPY packages/database/src packages/database/src
COPY packages/database/tsconfig.json packages/database/
COPY packages/llm/src packages/llm/src
COPY packages/llm/tsconfig.json packages/llm/
COPY packages/makedata/src packages/makedata/src
COPY packages/makedata/tsconfig.json packages/makedata/

COPY apps/backend/src apps/backend/src
COPY apps/backend/tsconfig.json apps/backend/

RUN pnpm turbo build --filter=eval-platform-backend

EXPOSE 8100

ENV NODE_ENV=production

CMD ["npx", "tsx", "apps/backend/dist/index.js"]