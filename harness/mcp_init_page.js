// Playwright MCP（.mcp.json の --init-page）：開いたページは *.supabase.co/storage/ を取りに行かない（灰色の画像を返す）。
// 係が本番の画面を自分で開くとき写真の配信（月 5 GB の枠）を食わないため。docs/rules/free-tier.md 決まり 1
const GRAY = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEUlEQVR4nGNoaGgYFUQAANbVRbl3EF3BAAAAAElFTkSuQmCC', 'base64');
module.exports = {
  default: async ({ page }) => {
    await page.route(/^https:\/\/[^/]+\.supabase\.co\/storage\//, (r) => r.fulfill({ status: 200, body: GRAY, contentType: 'image/png' }));
  },
};
