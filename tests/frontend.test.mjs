// Run with Node 20+ and Playwright installed. Optional PLAYWRIGHT_MODULE and
// CHROME_EXECUTABLE variables select existing installations; no download occurs.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

test("category selector browser interactions and ComfyUI adapter compatibility", async t => {
  const server = createServer(async (request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    if (pathname === "/scripts/app.js") {
      response.writeHead(200, { "Content-Type": "text/javascript" });
      return response.end("globalThis.__extensions = []; export const app = { registerExtension(extension) { globalThis.__extensions.push(extension); } };");
    }
    const relative = pathname.startsWith("/extensions/danbooru/")
      ? `web/${pathname.slice("/extensions/danbooru/".length)}`
      : "tests/frontend-harness.html";
    const file = resolve(repo, relative);
    if (!file.startsWith(repo + sep)) { response.writeHead(403); return response.end(); }
    try {
      const body = await readFile(file);
      const extension = file.slice(file.lastIndexOf("."));
      response.writeHead(200, { "Content-Type": `${mime[extension] || "text/plain"}; charset=utf-8` });
      response.end(body);
    } catch {
      response.writeHead(404); response.end();
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
  const page = await browser.newPage({ viewport: { width: 1050, height: 850 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const base = `http://127.0.0.1:${server.address().port}`;
  const row = name => page.locator(".dts-row").filter({ has: page.locator(".dts-category", { hasText: name }) });
  const names = () => page.locator(".dts-row").evaluateAll(rows => rows.map(row => row.dataset.name));
  const rows = () => page.evaluate(() => fixture.rows());
  const mount = async (value = '["对象","特征","表情"]', categories = []) => {
    await page.evaluate(({ value, categories }) => fixture.mountPanel(value, categories), { value, categories });
  };

  try {
    await page.goto(base);
    await page.waitForFunction(() => Boolean(globalThis.fixture));

    await t.test("legacy values and custom mappings are parsed without executing content", async () => {
      const result = await page.evaluate(() => ({
        legacy: fixture.parseRows("['对象', '特征', '对象']"),
        objectRows: fixture.parseRows('[{"name":"关闭","enabled":false},{"name":"开启","enabled":true}]'),
        injected: fixture.parseRows("[globalThis.INJECTED = true]"),
        untouched: globalThis.INJECTED === undefined,
        mappings: fixture.mappingCategories("{('人物', '数量'): '自定义分类', ('a:b', 'x'): '名称:保留', ('a', 'c'): '自定义分类'}"),
      }));
      assert.deepEqual(result.legacy, [{ name: "对象", enabled: true }, { name: "特征", enabled: true }]);
      assert.deepEqual(result.objectRows, [{ name: "关闭", enabled: false }, { name: "开启", enabled: true }]);
      assert.deepEqual(result.injected, []);
      assert.equal(result.untouched, true);
      assert.deepEqual(result.mappings, ["自定义分类", "名称:保留"]);
    });

    await t.test("every mapping category is available and omitted categories start disabled", async () => {
      await mount('["对象"]', ["对象", "特征", "表情", "特征", "未归类词"]);
      assert.deepEqual(await names(), ["对象", "特征", "表情", "未归类词"]);
      assert.deepEqual((await rows()).map(row => row.enabled), [true, false, false, false]);
      await row("特征").locator(".dts-toggle").click();
      assert.equal((await rows())[1].enabled, true);
      assert.match(await page.locator(".dts-count").innerText(), /2 \/ 4/);
      await page.locator(".dts-all").click();
      assert.ok((await rows()).every(row => row.enabled));
      await page.locator(".dts-all").click();
      assert.ok((await rows()).every(row => !row.enabled));
      assert.equal(await page.evaluate(() => fixture.changes.length), 3);
    });

    await t.test("arrow movement, boundary buttons, keyboard toggling and focus", async () => {
      await mount();
      assert.equal(await row("对象").locator('[data-action="up"]').isDisabled(), true);
      assert.equal(await row("表情").locator('[data-action="down"]').isDisabled(), true);
      await row("特征").locator('[data-action="up"]').click();
      assert.deepEqual(await names(), ["特征", "对象", "表情"]);
      await row("特征").locator('[data-action="down"]').focus();
      await page.keyboard.press("Enter");
      assert.deepEqual(await names(), ["对象", "特征", "表情"]);
      assert.equal(await page.evaluate(() => document.activeElement?.dataset.action), "down");
      await row("特征").locator(".dts-toggle").focus();
      await page.keyboard.press("Space");
      assert.equal((await rows())[1].enabled, false);
      assert.equal(await page.evaluate(() => document.activeElement?.dataset.action), "toggle");
    });

    await t.test("dragging category labels changes serialized output order", async () => {
      await mount();
      await row("对象").locator(".dts-category").dragTo(row("表情"));
      assert.deepEqual(await names(), ["特征", "表情", "对象"]);
      assert.deepEqual((await rows()).map(row => row.name), ["特征", "表情", "对象"]);
      assert.equal(await page.locator(".dts-drop, .dts-dragging").count(), 0);
    });

    await t.test("disabled category previews, long tag expansion, stale state and safe text", async () => {
      await mount([{ name: "对象", enabled: true }, { name: "特征", enabled: false }]);
      const longTags = "blue_hair, long_hair, blue_eyes, hair_ornament, ".repeat(12) + '<img class="injected" src=x onerror="globalThis.INJECTED=true">';
      await page.evaluate(tags => fixture.panel.setPreview([{ name: "对象", tags: "1girl, solo" }, { name: "特征", tags }, { name: "新发现分类", tags: "new_tag" }]), longTags);
      assert.equal(await row("特征").locator(".dts-tags").innerText(), longTags);
      assert.equal((await rows())[1].enabled, false);
      assert.equal((await rows())[2].enabled, false);
      assert.equal(await page.locator("img.injected").count(), 0);
      const previousHeight = (await row("特征").boundingBox()).height;
      await row("特征").locator(".dts-tags").click();
      assert.equal(await row("特征").locator(".dts-tags").getAttribute("aria-expanded"), "true");
      assert.ok((await row("特征").boundingBox()).height > previousHeight * 2);
      assert.equal(await page.evaluate(() => document.activeElement?.dataset.action), "tags");
      await page.keyboard.press("Enter");
      assert.equal(await row("特征").locator(".dts-tags").getAttribute("aria-expanded"), "false");
      assert.equal(await page.evaluate(() => document.activeElement?.dataset.action), "tags");
      await page.evaluate(() => fixture.panel.markStale());
      assert.match(await page.locator(".dts-note").innerText(), /输入已改变/);
      await page.evaluate(() => fixture.panel.setPreview([{ name: "特征", tags: "updated_tag" }]));
      assert.equal(await row("特征").locator(".dts-tags").innerText(), "updated_tag");
      assert.doesNotMatch(await page.locator(".dts-note").innerText(), /输入已改变/);
    });

    await t.test("saved order and disabled state survive browser reload", async () => {
      await mount();
      await row("特征").locator(".dts-toggle").click();
      await row("表情").locator('[data-action="up"]').click();
      const expected = await rows();
      await page.evaluate(() => localStorage.setItem("saved_categories", fixture.panel.getValue()));
      await page.reload();
      await page.waitForFunction(() => Boolean(globalThis.fixture));
      await page.evaluate(() => fixture.mountPanel(localStorage.getItem("saved_categories")));
      assert.deepEqual(await rows(), expected);
    });

    await t.test("narrow panel retains readable labels and usable controls without horizontal scrolling", async () => {
      await mount('["这是非常长的自定义分类名称","对象"]');
      await page.evaluate(() => {
        document.getElementById("host").style.width = "280px";
        fixture.panel.setPreview([{ name: "这是非常长的自定义分类名称", tags: "long_tag_".repeat(60) }]);
      });
      const dimensions = await page.locator(".dts-row").first().evaluate(element => {
        const tags = element.querySelector(".dts-tags");
        const label = element.querySelector(".dts-category");
        return { width: element.clientWidth, scroll: element.scrollWidth, tags: tags.getBoundingClientRect().width, label: label.getBoundingClientRect().width, labelOverflow: getComputedStyle(label).textOverflow };
      });
      assert.ok(dimensions.scroll <= dimensions.width + 1, JSON.stringify(dimensions));
      assert.ok(dimensions.tags > 35, JSON.stringify(dimensions));
      assert.ok(dimensions.label <= 82, JSON.stringify(dimensions));
      assert.equal(dimensions.labelOverflow, "ellipsis");
      await page.evaluate(() => { document.getElementById("host").style.width = "520px"; });
    });

    await t.test("ComfyUI replacement keeps all 11 legacy input indices and cleans up the old DOM lifecycle", async () => {
      const result = await page.evaluate(() => {
        const node = fixture.mountNode();
        return {
          names: node.widgets.map(widget => widget.name),
          values: node.widgets.map(widget => widget.value),
          oldRegistered: node.registered.has(node.originalOrder),
          registered: node.registered.size,
          removed: node.originalOrder.removeCount,
          created: node.oldCalls.created,
          legacyNames: fixture.legacyNames,
          legacyValues: fixture.legacyValues,
        };
      });
      assert.deepEqual(result.names, result.legacyNames);
      assert.equal(result.names.length, 11);
      result.values.forEach((value, index) => { if (index !== 3) assert.deepEqual(value, result.legacyValues[index]); });
      assert.equal(result.oldRegistered, false, "the original textarea must not be registered again by its onAdded callback");
      assert.equal(result.registered, 1);
      assert.ok(result.removed >= 1);
      assert.equal(result.created, 1);
    });

    await t.test("ComfyUI restore, custom mapping changes, preview events and connections", async () => {
      await page.evaluate(() => {
        const node = fixture.mountNode();
        const values = fixture.legacyValues.slice();
        values[3] = JSON.stringify([{ name: "角色表情词", enabled: false }, { name: "人物对象词", enabled: true }]);
        node.configure(values);
      });
      assert.deepEqual((await names()).slice(0, 2), ["角色表情词", "人物对象词"]);
      assert.equal(await row("角色表情词").locator(".dts-toggle").getAttribute("aria-checked"), "false");
      await page.evaluate(() => {
        const widget = fixture.node.widgets.find(widget => widget.name === "category_mapping");
        widget.value += ", ('自定义', 'a'): '服饰词'";
        widget.callback();
        fixture.node.onExecuted({ category_preview: [[{ name: "角色表情词", tags: "smile" }, { name: "服饰词", tags: "dress" }]] });
      });
      assert.ok((await names()).includes("服饰词"));
      assert.equal(await row("角色表情词").locator(".dts-tags").innerText(), "smile");
      assert.equal(await row("服饰词").locator(".dts-tags").innerText(), "dress");
      await row("服饰词").locator(".dts-toggle").click();
      assert.ok(await page.evaluate(() => fixture.node.changes > 0));
      await page.evaluate(() => {
        fixture.node.inputs = [{ name: "new_category_order", link: 1 }];
        fixture.node.onConnectionsChange();
      });
      assert.equal(await page.locator(".dts-all").isDisabled(), true);
      assert.equal(await row("服饰词").locator(".dts-toggle").isDisabled(), true);
      assert.equal(await row("服饰词").locator(".dts-category").getAttribute("draggable"), "false");
      assert.match(await page.locator(".dts-note").innerText(), /输入连线/);
      const state = await page.evaluate(() => {
        fixture.node.onRemoved();
        return { calls: fixture.node.oldCalls, registered: fixture.node.registered.size };
      });
      assert.deepEqual(state.calls, { created: 1, configured: 1, executed: 1, connected: 1 });
      assert.equal(state.registered, 0);
    });

    await t.test("connected preview uses upstream order without changing local selection", async () => {
      const saved = await page.evaluate(() => {
        const node = fixture.mountNode();
        const value = node.widgets[3].value;
        node.inputs = [{ name: "new_category_order", link: 1 }];
        node.onConnectionsChange();
        node.onExecuted({ category_preview: [[{ name: "上游第二类", tags: "b" }, { name: "上游第一类", tags: "a" }]] });
        return value;
      });
      assert.deepEqual(await names(), ["上游第二类", "上游第一类"]);
      assert.equal(await page.locator(".dts-count").innerText(), "由输入连线提供");
      assert.equal(await page.locator(".dts-toggle").first().isVisible(), false);
      assert.equal(await page.evaluate(() => fixture.node.widgets[3].value), saved);
      await page.evaluate(() => {
        fixture.node.inputs[0].link = null;
        fixture.node.onConnectionsChange();
      });
      assert.deepEqual(await names(), JSON.parse(saved).map(row => row.name));
      assert.equal(await page.locator(".dts-toggle").first().isVisible(), true);
    });

    await t.test("converted input metadata and legacy removal fallback preserve the replacement", async () => {
      for (const legacyRemove of [false, true]) {
        const state = await page.evaluate(legacyRemove => {
          const node = fixture.mountNode(undefined, { convertedSlot: true, legacyRemove });
          const widget = node.widgets[3];
          const result = {
            count: node.widgets.length,
            slotName: node.inputs[0].widget?.name,
            rebound: node.inputs[0]._widget === widget,
            oldHidden: node.originalOrder.hidden,
            oldRegistered: node.registered.has(node.originalOrder),
            savedValue: widget.value,
            hasSizer: typeof widget.computeSize === "function",
            minHeight: widget.options.getMinHeight(),
          };
          node.onRemoved();
          result.registeredAfterRemoval = node.registered.size;
          return result;
        }, legacyRemove);
        assert.equal(state.count, 11);
        assert.equal(state.slotName, "new_category_order");
        assert.equal(state.rebound, true);
        assert.equal(state.oldHidden, true);
        assert.equal(state.oldRegistered, false);
        assert.ok(JSON.parse(state.savedValue).some(row => row.name === "人物对象词"));
        assert.equal(state.hasSizer, true);
        assert.ok(state.minHeight > 0);
        assert.equal(state.registeredAfterRemoval, 0);
      }
    });

    await t.test("undo transactions capture changes before and after edits, excluding preview and restoration", async () => {
      await page.evaluate(() => {
        const node = fixture.mountNode();
        node.configure(fixture.legacyValues);
        node.onExecuted({ category_preview: [{ name: "人物对象词", tags: "1girl" }] });
      });
      assert.deepEqual(await page.evaluate(() => fixture.node.transactions), []);
      await row("人物对象词").locator(".dts-tags").click();
      assert.deepEqual(await page.evaluate(() => fixture.node.transactions), []);
      await row("人物对象词").locator(".dts-toggle").click();
      let transactions = await page.evaluate(() => fixture.node.transactions);
      assert.deepEqual(transactions.map(item => item.phase), ["before", "after"]);
      assert.equal(transactions[0].rows.find(item => item.name === "人物对象词").enabled, true);
      assert.equal(transactions[1].rows.find(item => item.name === "人物对象词").enabled, false);

      await page.locator(".dts-all").click();
      await row("角色表情词").locator('[data-action="up"]').click();
      await row("人物对象词").locator(".dts-category").dragTo(row("角色特征词"));
      transactions = await page.evaluate(() => fixture.node.transactions);
      assert.equal(transactions.length, 8);
      assert.deepEqual(transactions.map(item => item.phase), ["before", "after", "before", "after", "before", "after", "before", "after"]);
      for (let index = 0; index < transactions.length; index += 2) {
        assert.notDeepEqual(transactions[index].rows, transactions[index + 1].rows);
        if (index > 0) assert.deepEqual(transactions[index - 1].rows, transactions[index].rows);
      }
      assert.deepEqual(transactions.at(-1).rows, await page.evaluate(() => JSON.parse(fixture.node.widgets[3].value)));
    });

    assert.deepEqual(errors, [], "browser must not report uncaught errors");
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
});
