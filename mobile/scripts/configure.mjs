import fs from "node:fs";
import process from "node:process";

const raw = process.env.LLCC_SERVER_URL ?? "";
if (!raw) throw new Error("LLCC_SERVER_URL is required.");
const url = new URL(raw);
if (url.protocol !== "https:") throw new Error("LLCC_SERVER_URL must use HTTPS.");
if (url.username || url.password) throw new Error("Credentials must not be embedded in LLCC_SERVER_URL.");

const template = fs.readFileSync(new URL("../capacitor.config.template.json", import.meta.url), "utf8");
const output = template
  .replaceAll("__LLCC_SERVER_URL__", url.origin + url.pathname.replace(/\/$/, ""))
  .replaceAll("__LLCC_SERVER_HOST__", url.host);
fs.writeFileSync(new URL("../capacitor.config.json", import.meta.url), output);
console.log(`Configured secure server: ${url.host}`);
