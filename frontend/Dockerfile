FROM node:20-slim
WORKDIR /app

COPY package*.json ./
# Build ke liye devDependencies zaroori hain
RUN npm install

COPY . .
RUN npm run build

# Runtime par sirf production packages rakhein
ENV NODE_ENV=production
RUN npm prune --production

EXPOSE 3000
CMD ["npm", "start"]
