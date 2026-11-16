import { createClient } from "npm:@supabase/supabase-js@2";

const RENDER_ID_PATTERN = /^R[A-Z0-9]{4,31}$/;
const encoder = new TextEncoder();

function jsonResponse(body: Record<string, unknown>, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

async function secretsMatch(supplied: string, expected: string): Promise<boolean> {
  const [suppliedHash, expectedHash] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(supplied)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const suppliedBytes = new Uint8Array(suppliedHash);
  const expectedBytes = new Uint8Array(expectedHash);
  let difference = 0;
  for (let index = 0; index < suppliedBytes.length; index += 1) {
    difference |= suppliedBytes[index] ^ expectedBytes[index];
  }
  return difference === 0;
}

function renderIdFromPath(pathname: string): string | null {
  const parts = pathname.split("/").filter(Boolean);
  const functionIndex = parts.lastIndexOf("render-status");
  const route = functionIndex >= 0 ? parts.slice(functionIndex + 1) : parts;
  if (
    route.length !== 4 || route[0] !== "api" || route[1] !== "renders" ||
    route[3] !== "status"
  ) {
    return null;
  }
  const renderId = route[2].trim().toUpperCase();
  return RENDER_ID_PATTERN.test(renderId) ? renderId : null;
}

function serverOnlySupabaseKey(): string {
  const currentKeys = Deno.env.get("SUPABASE_SECRET_KEYS");
  if (currentKeys) {
    try {
      const parsed = JSON.parse(currentKeys) as Record<string, unknown>;
      if (typeof parsed.default === "string") return parsed.default;
    } catch {
      return "";
    }
  }
  return Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
}

Deno.serve(async (request: Request) => {
  if (request.method !== "GET") {
    return jsonResponse({ detail: "Method not allowed." }, 405);
  }

  const renderId = renderIdFromPath(new URL(request.url).pathname);
  if (!renderId) {
    return jsonResponse({ detail: "Render not found." }, 404);
  }

  const apiKey = Deno.env.get("RENDER_STATUS_API_KEY") ?? "";
  const allowedTeam = Deno.env.get("RENDER_STATUS_ALLOWED_TEAM_ID") ?? "";
  const allowedChannels = new Set(
    (Deno.env.get("RENDER_STATUS_ALLOWED_CHANNEL_IDS") ?? "")
      .split(",").map((value) => value.trim()).filter(Boolean),
  );
  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const serverKey = serverOnlySupabaseKey();
  if (
    !apiKey || !allowedTeam || allowedChannels.size === 0 ||
    !supabaseUrl || !serverKey
  ) {
    return jsonResponse({ detail: "Render status API is not configured." }, 503);
  }

  const authorization = request.headers.get("authorization") ?? "";
  const suppliedKey = authorization.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length)
    : "";
  if (!suppliedKey || !(await secretsMatch(suppliedKey, apiKey))) {
    return jsonResponse({ detail: "Invalid API credentials." }, 401);
  }

  const teamId = request.headers.get("x-renderpulse-slack-team") ?? "";
  const channelId = request.headers.get("x-renderpulse-slack-channel") ?? "";
  if (!(await secretsMatch(teamId, allowedTeam)) || !allowedChannels.has(channelId)) {
    return jsonResponse({ detail: "Render status access is not allowed." }, 403);
  }

  const supabase = createClient(supabaseUrl, serverKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await supabase
    .from("render_jobs")
    .select("render_id,status,progress,model_format,updated_at")
    .eq("render_id", renderId)
    .maybeSingle();

  if (error) {
    console.error("Render status lookup failed", { code: error.code });
    return jsonResponse({ detail: "Render status lookup failed." }, 500);
  }
  if (!data) {
    return jsonResponse({ detail: "Render not found." }, 404);
  }

  const response: Record<string, unknown> = {
    render_id: data.render_id,
    status: data.status,
    updated_at: data.updated_at,
  };
  if (data.progress !== null) response.progress = data.progress;
  if (data.model_format !== null) response.model_format = data.model_format;
  return jsonResponse(response, 200);
});
