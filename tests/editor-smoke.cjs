const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  let browser;
  try { browser = await chromium.launch(); }
  catch (error) {
    if (/Executable doesn't exist|Please run.*playwright install/.test(error.message)) process.exit(77);
    throw error;
  }
  try {
    const page = await browser.newPage({viewport: {width: 1380, height: 960}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.goto(process.argv[2]);
    await page.waitForSelector('canvas[data-drawn="true"]');
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Ready.'));
    const drawn = await page.locator('canvas').evaluate(canvas => {
      const {data} = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
      let cyan = 0, bright = 0;
      for (let i = 0; i < data.length; i += 4) {
        if (data[i] < 100 && data[i + 1] > 150 && data[i + 2] > 150) cyan++;
        if (data[i] > 180 && data[i + 1] > 180 && data[i + 2] > 180) bright++;
      }
      return {cyan, bright, width: canvas.width, height: canvas.height};
    });
    assert.ok(drawn.width > 500 && drawn.height > 300);
    assert.ok(drawn.bright > 0, 'measure labels and notes should be drawn');
    await page.locator('[name="title"]').fill('Gram · browser edit');
    await page.locator('[name="title"]').press('Tab');
    await page.waitForFunction(() => document.getElementById('dirty').textContent === 'Unsaved changes');
    await page.locator('#save').click();
    await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Saved '));
    assert.equal((await (await page.request.get(process.argv[2] + '/api/chart')).json()).meta.title, 'Gram · browser edit');
    // Undo metadata and redo using actual keyboard shortcuts on the canvas.
    await page.locator('canvas').focus();
    await page.keyboard.press('Control+z');
    assert.equal(await page.locator('[name="title"]').inputValue(), 'Gram');
    await page.keyboard.press('Control+y');
    assert.equal(await page.locator('[name="title"]').inputValue(), 'Gram · browser edit');
    await page.locator('#draft-tab').click();
    await page.waitForFunction(() => document.getElementById('draft').value.includes('title:'));
    await page.locator('#draft').fill('bad header');
    await page.locator('#apply').click();
    await page.waitForFunction(() => document.getElementById('draft-errors').textContent.includes('Line 1:'));
    await page.locator('#decompile').click();
    await page.waitForFunction(() => document.getElementById('draft').value.includes('title:'));
    await page.locator('#apply').click();
    await page.waitForFunction(() => document.getElementById('status').textContent === 'Draft applied.');
    await page.locator('#inspect-tab').click();
    await page.locator('#play').click();
    await page.waitForFunction(() => document.getElementById('audio').currentTime > 0.1);
    await page.locator('#rate').selectOption('0.75');
    assert.equal(await page.locator('#audio').evaluate(audio => audio.playbackRate), 0.75);
    await page.locator('#play').click();
    const box = await page.locator('canvas').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.keyboard.down('Control'); await page.mouse.wheel(0, -100); await page.keyboard.up('Control');
    await page.waitForFunction(() => document.getElementById('zoom').textContent !== '100%');
    fs.mkdirSync('out', {recursive: true});
    await page.screenshot({path: 'out/editor-preview.png', fullPage: true});
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
