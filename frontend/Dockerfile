FROM node:20-bookworm-slim AS build

WORKDIR /app
COPY frontend/package.json frontend/yarn.lock ./
RUN corepack enable \
    && yarn install --frozen-lockfile --ignore-scripts

COPY frontend ./
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}
RUN CI=true yarn build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1
