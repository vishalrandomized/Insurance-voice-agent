# Next.js web for Railway (all-on-Railway, no Vercel).
#
# Railway settings for THIS service:
#   - Root Directory: the REPO ROOT (leave blank / "/")
#   - Variable: RAILWAY_DOCKERFILE_PATH = apps/web/Dockerfile
# so the build context is the repo root and the @insurance/contracts workspace
# is available to the build.
FROM node:20-slim AS build
WORKDIR /repo

# Install workspace deps (layer-cached on the manifests).
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci

# Next.js inlines NEXT_PUBLIC_* at BUILD time. Railway passes service variables
# as build args, so declare and promote them to env before building.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

COPY packages/contracts packages/contracts
COPY apps/web apps/web
RUN npm run build:web

FROM node:20-slim AS run
WORKDIR /repo
ENV NODE_ENV=production
COPY --from=build /repo ./
WORKDIR /repo/apps/web
EXPOSE 3000
# next start binds 0.0.0.0 by default; shell form expands Railway's $PORT.
CMD ["sh", "-c", "npm run start -- -p ${PORT:-3000}"]
