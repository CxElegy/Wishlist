// 截图：node shot.mjs <html 绝对路径> <输出.png> [宽度]
// 需要 playwright（npm i playwright）；云端环境已装好 Chromium，不要 playwright install
import { chromium } from 'playwright';
const [file, out, width = 2200] = process.argv.slice(2);
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' }).catch(() => chromium.launch());
const p = await b.newPage({ viewport: { width: +width, height: 900 } });
await p.goto('file://' + file, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => console.log('goto', e.message));
await p.waitForTimeout(1500);
await p.screenshot({ path: out, fullPage: true });
await b.close();
console.log('→', out);
