FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Rewrites are resolved at build time, so the API address is a build argument.
ARG MOGUL_API_URL=http://api:8000
ENV MOGUL_API_URL=$MOGUL_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000 NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
