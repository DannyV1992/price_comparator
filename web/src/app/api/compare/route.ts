import { getOffers } from "@/lib/offers";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { ids?: unknown } | null;
  const ids = Array.isArray(body?.ids) ? body.ids.filter((id): id is string => typeof id === "string") : [];
  return Response.json({ offers: await getOffers(ids) });
}
