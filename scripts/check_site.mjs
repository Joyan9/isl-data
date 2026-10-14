// Development-only browser check. Run after generating site/ with:
// node scripts/check_site.mjs site
import { chromium } from "playwright";
import { resolve } from "node:path";

const root = resolve(process.argv[2] || "site");
const browser = await chromium.launch({ headless: true });
const widths = [390, 1280];
const failures = [];
for (const width of widths) {
const page = await browser.newPage({ viewport: { width, height: 900 } });
await page.goto(`file://${root}/index.html`);
await page.waitForFunction(() => document.querySelectorAll(".comparison-summary .compare-track").length > 0);

const result = await page.evaluate(() => {
  const parse = (value) => {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const parts = match[1].split(",").map(Number);
    return [parts[0], parts[1], parts[2], parts[3] ?? 1];
  };
  const luminance = (color) => {
    const rgb = parse(color);
    if (!rgb) return null;
    return rgb.slice(0, 3).map((value) => value / 255).map((value) =>
      value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
    ).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
  };
  const contrast = (foreground, background) => {
    const fg = luminance(foreground), bg = luminance(background);
    return fg === null || bg === null ? 0 : (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
  };
  const visibleText = [...document.querySelectorAll("body *")].filter((node) =>
    node.children.length === 0 && node.textContent.trim() && node.getClientRects().length
  );
  const contrastFailures = visibleText.filter((node) => {
    const style = getComputedStyle(node);
    return contrast(style.color, style.backgroundColor === "rgba(0, 0, 0, 0)"
      ? getComputedStyle(node.parentElement).backgroundColor : style.backgroundColor) < 4.5;
  }).map((node) => node.textContent.trim());
  const barFailures = [...document.querySelectorAll(".compare-track, .xg-bars i")].filter((bar) => {
    const fills = [...bar.querySelectorAll(".compare-segment, em")];
    return fills.some((fill) => parseFloat(getComputedStyle(fill).width) > 0 &&
      getComputedStyle(fill).backgroundColor === "rgba(0, 0, 0, 0)");
  }).length;
  return { contrastFailures, barFailures };
});
if (result.contrastFailures.length || result.barFailures) failures.push({ width, ...result });
await page.close();
}
await browser.close();
if (failures.length) {
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
}
console.log("site accessibility and bar checks passed");
