import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const source = resolve(root, "outputs");
const target = resolve(root, "dist");

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
await mkdir(resolve(target, ".openai"), { recursive: true });
await cp(resolve(root, ".openai", "hosting.json"), resolve(target, ".openai", "hosting.json"));

const files = ["index.html", "sector_real_data.js", "sector_real_data.json", "market_modules_data.js", "market_modules_data.json"];
const assets = {};
for (const file of files) {
  assets[`/${file}`] = await readFile(resolve(source, file), "utf8");
}

const server = `const assets = ${JSON.stringify(assets)};\n\nconst types = {\n  ".html": "text/html; charset=utf-8",\n  ".js": "text/javascript; charset=utf-8",\n  ".json": "application/json; charset=utf-8"\n};\n\nfunction contentType(pathname) {\n  const match = pathname.match(/\\.[^.]+$/);\n  return match ? types[match[0]] || "text/plain; charset=utf-8" : "text/plain; charset=utf-8";\n}\n\nexport default {\n  async fetch(request) {\n    const url = new URL(request.url);\n    const pathname = url.pathname === "/" ? "/index.html" : url.pathname;\n    const body = assets[pathname];\n    if (body === undefined) return new Response("Not found", { status: 404 });\n    return new Response(body, { headers: { "content-type": contentType(pathname), "cache-control": "no-store" } });\n  }\n};\n`;

await mkdir(resolve(target, "server"), { recursive: true });
await writeFile(resolve(target, "server", "index.js"), server, "utf8");
