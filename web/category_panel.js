// No eval: workflow configuration is data, including Python-style string lists.
const STRING_TOKEN = /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g;

function readString(token) {
    if (token.startsWith('"')) {
        try { return JSON.parse(token); } catch { /* Python escapes below. */ }
    }
    return token.slice(1, -1).replace(/\\(u[0-9a-fA-F]{4}|[\\'"nrt])/g, (_, c) => {
        if (c.startsWith("u")) return String.fromCharCode(parseInt(c.slice(1), 16));
        return ({ n: "\n", r: "\r", t: "\t" })[c] ?? c;
    });
}

export function parseRows(value) {
    let parsed = value;
    if (typeof value === "string") {
        try { parsed = JSON.parse(value); }
        catch {
            // Older workflows sometimes use single-quoted Python lists.
            const tokens = value.match(STRING_TOKEN) || [];
            const remainder = value.replace(STRING_TOKEN, "").replace(/[\[\],\s]/g, "");
            parsed = remainder ? [] : tokens.map(readString);
        }
    }
    if (!Array.isArray(parsed)) return [];
    const seen = new Set();
    return parsed.flatMap((item) => {
        const name = typeof item === "string" ? item : item?.name;
        if (typeof name !== "string" || !name.trim() || seen.has(name)) return [];
        seen.add(name);
        return [{ name, enabled: typeof item === "string" || item.enabled !== false }];
    });
}

export function mappingCategories(value) {
    if (value && typeof value === "object") return [...new Set(Object.values(value).filter(v => typeof v === "string"))];
    const names = [];
    // Tokenize first so a colon inside a category name cannot become a mapping.
    const tokens = String(value || "").match(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|:/g) || [];
    for (let i = 1; i < tokens.length; i++) {
        if (tokens[i - 1] === ":" && tokens[i] !== ":") names.push(readString(tokens[i]));
    }
    return [...new Set(names.filter(name => name.trim()))];
}

export function completeRows(rows, names) {
    const seen = new Set(rows.map(row => row.name));
    const result = rows.map(row => ({ ...row }));
    for (const name of names) {
        if (typeof name === "string" && name.trim() && !seen.has(name)) {
            seen.add(name);
            // Discover every category without silently enabling omitted categories.
            result.push({ name, enabled: false });
        }
    }
    return result;
}

export function createCategoryPanel({ value, onBeforeChange = () => {}, onChange = () => {}, onResize = () => {} } = {}) {
    const element = document.createElement("div");
    element.className = "danbooru-category-panel";
    element.setAttribute("aria-label", "分类选择与输出顺序");
    let rows = parseRows(value);
    let categoryNames = [];
    let preview = new Map();
    let hasPreview = false;
    let stale = false;
    let connected = false;
    let connectedRows = null;
    let dragged = null;
    const expanded = new Set();

    const makeButton = (label, className, text) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = className;
        button.title = label;
        button.setAttribute("aria-label", label);
        if (text) button.textContent = text;
        return button;
    };

    const notify = (focusName, focusAction) => {
        render();
        onChange(JSON.stringify(rows));
        if (focusName) {
            const row = [...element.querySelectorAll(".dts-row")].find(item => item.dataset.name === focusName);
            row?.querySelector(`[data-action="${focusAction}"]`)?.focus({ preventScroll: true });
        }
    };

    const move = (name, offset) => {
        const index = rows.findIndex(row => row.name === name);
        const target = index + offset;
        if (connected || index < 0 || target < 0 || target >= rows.length) return;
        onBeforeChange();
        const [row] = rows.splice(index, 1);
        rows.splice(target, 0, row);
        notify(name, offset < 0 ? "up" : "down");
    };

    function render() {
        const visibleRows = connected && connectedRows ? connectedRows : rows;
        element.dataset.connected = String(connected);
        const scroll = element.querySelector(".dts-rows")?.scrollTop || 0;
        element.replaceChildren();
        const header = document.createElement("div");
        header.className = "dts-header";
        const enabled = visibleRows.filter(row => row.enabled).length;
        const all = makeButton("切换全部分类", "dts-all");
        all.setAttribute("role", "switch");
        all.setAttribute("aria-checked", String(rows.length > 0 && enabled === rows.length));
        all.disabled = connected || !rows.length;
        const allTrack = document.createElement("span");
        allTrack.className = "dts-switch";
        allTrack.dataset.state = enabled === rows.length && rows.length ? "on" : enabled ? "mixed" : "off";
        const allLabel = document.createElement("span");
        allLabel.textContent = connected ? "分类预览" : "全部启用";
        all.append(allTrack, allLabel);
        all.onclick = () => {
            const next = enabled !== rows.length;
            onBeforeChange();
            rows = rows.map(row => ({ ...row, enabled: next }));
            notify();
            element.querySelector(".dts-all")?.focus({ preventScroll: true });
        };
        const count = document.createElement("span");
        count.className = "dts-count";
        count.textContent = connected ? "由输入连线提供" : `${enabled} / ${rows.length} 已启用`;
        header.append(all, count);
        const list = document.createElement("div");
        list.className = "dts-rows";
        list.setAttribute("role", "list");

        visibleRows.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = "dts-row";
            row.dataset.name = item.name;
            row.dataset.enabled = String(item.enabled);
            row.setAttribute("role", "listitem");
            const toggle = makeButton(`启用 ${item.name}`, "dts-toggle");
            toggle.dataset.action = "toggle";
            toggle.setAttribute("role", "switch");
            toggle.setAttribute("aria-checked", String(item.enabled));
            toggle.disabled = connected;
            const track = document.createElement("span");
            track.className = "dts-switch";
            track.dataset.state = item.enabled ? "on" : "off";
            toggle.append(track);
            toggle.onclick = () => { onBeforeChange(); item.enabled = !item.enabled; notify(item.name, "toggle"); };

            const order = document.createElement("span");
            order.className = "dts-order";
            const up = makeButton(`上移 ${item.name}`, "dts-arrow", "▴");
            const down = makeButton(`下移 ${item.name}`, "dts-arrow", "▾");
            up.dataset.action = "up";
            down.dataset.action = "down";
            up.disabled = connected || index === 0;
            down.disabled = connected || index === rows.length - 1;
            up.onclick = () => move(item.name, -1);
            down.onclick = () => move(item.name, 1);
            order.append(up, down);

            const tags = makeButton(`展开 ${item.name} 的 tag`, "dts-tags");
            tags.dataset.action = "tags";
            const text = preview.get(item.name) || "";
            tags.textContent = hasPreview ? text || "暂无 tag" : "运行后显示 tag";
            tags.title = text || tags.textContent;
            tags.dataset.empty = String(!text);
            tags.setAttribute("aria-expanded", String(expanded.has(item.name)));
            tags.onclick = () => {
                expanded.has(item.name) ? expanded.delete(item.name) : expanded.add(item.name);
                render();
                const current = [...element.querySelectorAll(".dts-row")].find(r => r.dataset.name === item.name);
                current?.querySelector('[data-action="tags"]')?.focus({ preventScroll: true });
                onResize();
            };
            const label = document.createElement("span");
            label.className = "dts-category";
            label.textContent = item.name;
            label.title = `${item.name} · 拖动调整顺序`;
            label.draggable = !connected;
            label.addEventListener("dragstart", event => {
                dragged = item.name;
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", item.name);
                row.classList.add("dts-dragging");
            });
            label.addEventListener("dragend", () => {
                dragged = null;
                element.querySelectorAll(".dts-drop, .dts-dragging").forEach(el => el.classList.remove("dts-drop", "dts-dragging"));
            });
            row.addEventListener("dragover", event => {
                if (connected || dragged === null || dragged === item.name) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                row.classList.add("dts-drop");
            });
            row.addEventListener("dragleave", event => {
                if (!row.contains(event.relatedTarget)) row.classList.remove("dts-drop");
            });
            row.addEventListener("drop", event => {
                event.preventDefault();
                if (connected || dragged === null || dragged === item.name) return;
                const from = rows.findIndex(r => r.name === dragged);
                const to = rows.findIndex(r => r.name === item.name);
                if (from < 0 || to < 0) return;
                onBeforeChange();
                const [moved] = rows.splice(from, 1);
                rows.splice(to, 0, moved);
                dragged = null;
                notify(moved.name, "toggle");
            });
            row.append(toggle, order, tags, label);
            list.append(row);
        });

        const note = document.createElement("div");
        note.className = "dts-note";
        note.textContent = connected ? "分类选择由输入连线提供" : stale ? "输入已改变 · 运行后更新 tag 预览" : "从上到下输出 · 箭头或拖动分类名排序";
        element.append(header, list, note);
        list.scrollTop = scroll;
    }

    // Keep ComfyUI canvas gestures from stealing widget interactions.
    for (const event of ["pointerdown", "mousedown", "dblclick", "keydown"]) {
        element.addEventListener(event, e => e.stopPropagation());
    }
    element.addEventListener("wheel", event => {
        const list = element.querySelector(".dts-rows");
        if (list && list.scrollHeight > list.clientHeight) event.stopPropagation();
    }, { passive: true });

    render();
    return {
        element,
        getValue: () => JSON.stringify(rows),
        setValue(value) { rows = completeRows(parseRows(value), categoryNames); render(); },
        setCategories(names) { categoryNames = names; rows = completeRows(rows, names); render(); },
        setConnected(value) {
            if (connected !== Boolean(value)) connectedRows = null;
            connected = Boolean(value);
            render();
        },
        markStale() { if (hasPreview) { stale = true; render(); } },
        setPreview(items) {
            if (!Array.isArray(items)) return;
            const valid = items.filter(item => item && typeof item.name === "string" && typeof item.tags === "string");
            preview = new Map(valid.map(item => [item.name, item.tags]));
            if (connected) connectedRows = valid.map(item => ({ name: item.name, enabled: true }));
            else rows = completeRows(rows, valid.map(item => item.name));
            hasPreview = true;
            stale = false;
            render();
        },
    };
}
