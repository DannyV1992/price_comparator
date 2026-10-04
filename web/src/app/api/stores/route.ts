import { getStores } from "@/lib/search";

export async function GET() {
  return Response.json({ stores: await getStores() });
}
