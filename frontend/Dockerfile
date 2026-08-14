# --- Шаг 1: Сборка React приложения ---
FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .
RUN npm run build

# --- Шаг 2: Раздача через Nginx ---
FROM nginx:alpine

# Копируем собранный билд в папки nginx
COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]