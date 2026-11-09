FROM node:22-alpine

# git: o Baileys puxa dependências direto do GitHub
RUN apk add --no-cache git

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY index.js ./

# Sessão do WhatsApp (credenciais do aparelho conectado): precisa de volume, senão pede QR a cada recriação
ENV AUTH_DIR=/data/auth
RUN mkdir -p /data/auth
VOLUME ["/data"]

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1

CMD ["node", "index.js"]
