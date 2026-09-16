/* Opens the Meta app dashboard using the user's own Chrome profile and screenshots it.
   Read-only reconnaissance: it navigates and captures, it does not click anything. */
const { chromium } = require('playwright');
const PROFILE_ROOT = process.env.HOME + '/Library/Application Support/Google/Chrome';
const PROFILE = process.argv[2] || 'Default';
const URL = process.argv[3] || 'https://developers.facebook.com/apps/';

(async () => {
  const ctx = await chromium.launchPersistentContext(PROFILE_ROOT, {
    channel: 'chrome',
    headless: false,
    args: [`--profile-directory=${PROFILE}`],
    viewport: { width: 1440, height: 900 },
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);
  console.log('URL   :', page.url());
  console.log('TITLE :', await page.title());
  // Is this a login wall or a real dashboard?
  const loggedOut = /login|checkpoint/i.test(page.url());
  console.log('LOGGED_IN:', !loggedOut);
  await page.screenshot({ path: '/tmp/claude-501/meta/dash.png', fullPage: false });
  console.log('SHOT  : /tmp/claude-501/meta/dash.png');
  await ctx.close();
})().catch(e => { console.error('ERR:', e.message.split('\n')[0]); process.exit(1); });
