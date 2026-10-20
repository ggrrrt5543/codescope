import { chromium } from 'playwright';
import fs from 'node:fs/promises';
const output = process.env.SCREENSHOT_DIR || 'reports';
await fs.mkdir(output, {recursive: true});
const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--no-sandbox']});
const page = await browser.newPage({viewport: {width: 1440, height: 1100}, colorScheme: 'light'});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto('http://127.0.0.1:8765/');
  await page.getByRole('button', {name: 'Проверить код'}).click();
  await page.waitForFunction(() => document.querySelector('#progress').textContent === 'Проверка завершена', {timeout: 90000});
  if (Number(await page.locator('#error-count').innerText()) < 1) throw new Error('Python errors absent');
  await page.locator('.finding-location').first().click();
  if (!(await page.locator('#code').evaluate(el => el.selectionEnd > el.selectionStart))) throw new Error('Line selection failed');
  await page.locator('#code').blur();
  await page.screenshot({path: `${output}/interface-desktop.png`, fullPage: true});
  await page.locator('#theme').click();
  await page.screenshot({path: `${output}/interface-dark.png`, fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile overflow');
  await page.screenshot({path: `${output}/interface-mobile.png`, fullPage: true});
  await page.locator('#theme').click();
  for (const language of ['cpp', 'csharp', 'java']) {
    await page.selectOption('#language', language);
    await page.getByRole('button', {name: 'Проверить код'}).click();
    await page.waitForFunction(() => document.querySelector('#progress').textContent === 'Проверка завершена', {timeout: 90000});
    if (Number(await page.locator('#error-count').innerText()) < 1) throw new Error(`${language}: errors absent`);
  }
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', {name: 'Скачать HTML'}).click();
  const download = await downloadEvent;
  await download.saveAs(`${output}/example-report.html`);
  await page.fill('#code', 'public class Main {}');
  if (!(await page.locator('#export-json').isDisabled())) throw new Error('Stale report export available');
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('UI: four languages, line navigation, export, stale-result guard, themes, mobile overflow — passed');
} finally {
  await browser.close();
}
