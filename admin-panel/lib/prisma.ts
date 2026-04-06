import { PrismaClient } from '@prisma/client'

let prisma: PrismaClient | null = null;

function getPrisma(): PrismaClient {
  if (!prisma) {
    try {
      prisma = new PrismaClient();
    } catch (e) {
      console.error('Prisma init error:', e);
      throw e;
    }
  }
  return prisma;
}

export default getPrisma();
export { getPrisma };
