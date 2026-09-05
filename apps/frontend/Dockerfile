FROM node:22-alpine AS build

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
WORKDIR /workspace

COPY package.json package-lock.json ./
COPY apps/frontend/package.json apps/frontend/package.json
RUN npm ci

COPY apps/frontend apps/frontend
RUN npm run build --workspace @intelligent-quant/frontend

FROM nginx:1.29-alpine

COPY deploy/regression/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/apps/frontend/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=5 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1
