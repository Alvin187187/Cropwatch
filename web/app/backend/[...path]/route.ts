import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const HOP_BY_HOP = ["connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length", "host"];

async function proxy(request: NextRequest, path: string[]) {
  const base = (process.env.API_INTERNAL_URL || "http://localhost:8000").replace(/\/$/, "");
  const target = `${base}/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);
  for (const name of HOP_BY_HOP) headers.delete(name);
  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
    });
    const outgoing = new Headers(response.headers);
    for (const name of HOP_BY_HOP) outgoing.delete(name);
    return new NextResponse(response.body, { status: response.status, headers: outgoing });
  } catch {
    return NextResponse.json({ detail: "The risk service is not reachable yet. Wait a moment and try again." }, { status: 502 });
  }
}

type Context = { params: { path: string[] } };

export function GET(request: NextRequest, context: Context) {
  return proxy(request, context.params.path);
}
export function POST(request: NextRequest, context: Context) {
  return proxy(request, context.params.path);
}
export function PUT(request: NextRequest, context: Context) {
  return proxy(request, context.params.path);
}
export function PATCH(request: NextRequest, context: Context) {
  return proxy(request, context.params.path);
}
export function DELETE(request: NextRequest, context: Context) {
  return proxy(request, context.params.path);
}
