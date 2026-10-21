FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
RUN addgroup -S openjobs && adduser -S openjobs -G openjobs && chown -R openjobs:openjobs /app
USER openjobs
EXPOSE 3000
CMD ["node", "server.js"]
