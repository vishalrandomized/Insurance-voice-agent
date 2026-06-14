import { CustomerCallRoom } from "../../components/customer/customer-call-room";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

type CustomerPageProps = {
  searchParams?: Promise<{
    session?: string;
    name?: string;
    product?: string;
  }>;
};

export default async function CustomerPage({
  searchParams,
}: CustomerPageProps) {
  const params = (await searchParams) ?? {};
  let sessionId = params.session;

  if (!sessionId) {
    try {
      const response = await fetch(`${API_URL}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: params.name ?? null,
          phone: null,
        }),
        cache: "no-store",
      });
      if (response.ok) {
        const data = (await response.json()) as {
          session_id?: string;
          sessionId?: string;
        };
        sessionId = data.session_id ?? data.sessionId;
      }
    } catch {
      // The UUID fallback keeps the interface usable before the API starts.
    }
  }

  return (
    <CustomerCallRoom
      sessionId={sessionId || "00000000-0000-4000-8000-000000000001"}
      customerName={params.name}
      productName={params.product}
    />
  );
}
