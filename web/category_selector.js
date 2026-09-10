import { app } from "../../scripts/app.js";
import { createCategoryPanel, mappingCategories } from "./category_panel.js";

const stylesheet = document.createElement("link");
stylesheet.rel = "stylesheet";
stylesheet.href = new URL("./category_panel.css", import.meta.url).href;
document.head.append(stylesheet);

const PANEL = Symbol("danbooruCategoryPanel");
const field = (node, name) => node.widgets?.find(widget => widget.name === name);

function labelOutputs(node) {
    const labels = { "分类数据包": "分类数据包 · Getter", ALL_TAGS: "ALL_TAGS · 已选 tag" };
    for (const output of node.outputs || []) {
        if (labels[output.name] && (!output.label || output.label === output.name)) {
            output.label = labels[output.name];
        }
    }
}

function installPanel(node) {
    if (node[PANEL]) return;
    const old = field(node, "new_category_order");
    if (!old || !node.addDOMWidget) return;
    const index = node.widgets.indexOf(old);
    const originalValue = old.value;
    const panel = createCategoryPanel({
        value: originalValue,
        onBeforeChange: () => node.graph?.beforeChange?.(),
        onChange: () => {
            node.graph?.afterChange?.();
            node.graph?.change?.();
            node.setDirtyCanvas?.(true, true);
        },
        onResize: () => node.setDirtyCanvas?.(true, true),
    });
    // Replace, rather than insert, so every legacy widgets_values index is stable.
    const slot = node.inputs?.find(input => input.name === "new_category_order");
    const slotWidget = slot?.widget;
    old.hidden = true;
    old.type = "hidden";
    old.computeSize = () => [0, 0];
    if (old.element) old.element.style.display = "none";
    if (typeof node.removeWidget === "function") node.removeWidget(old);
    else { node.widgets.splice(index, 1); old.onRemove?.(); }
    old.inputEl?.remove();
    old.element?.remove();
    const widget = node.addDOMWidget("new_category_order", "STRING", panel.element, {
        getValue: panel.getValue,
        setValue: panel.setValue,
        getMinHeight: () => 220,
        getMaxHeight: () => 640,
        getHeight: () => 540,
        hideOnZoom: false,
    });
    widget.serialize = true;
    widget.options = { ...widget.options, multiline: true };
    widget.computeSize = width => [width, 540];
    node.widgets.splice(node.widgets.indexOf(widget), 1);
    node.widgets.splice(index, 0, widget);
    if (slotWidget) {
        slot.widget = slotWidget;
        slot._widget = widget;
    }
    // Current ComfyUI retains an onAdded closure for the removed DOM widget.
    const added = node.onAdded;
    node.onAdded = function (...args) {
        const result = added?.apply(this, args);
        old.onRemove?.();
        old.inputEl?.remove();
        old.element?.remove();
        return result;
    };
    node[PANEL] = panel;

    const refreshCategories = () => {
        panel.setCategories([
            ...mappingCategories(field(node, "category_mapping")?.value, true),
            field(node, "default_category")?.value || "未归类词",
        ]);
        panel.setConnected(node.inputs?.some(input => input.name === "new_category_order" && input.link != null));
    };
    panel.refreshCategories = refreshCategories;
    for (const name of ["tags", "excel_file", "category_mapping", "default_category", "regex_blacklist", "tag_blacklist", "deduplicate_tags", "danbooru_lookup"]) {
        const watched = field(node, name);
        if (!watched) continue;
        const changed = () => {
            if (name === "category_mapping" || name === "default_category") refreshCategories();
            panel.markStale();
        };
        const callback = watched.callback;
        watched.callback = function (...args) { const result = callback?.apply(this, args); changed(); return result; };
        // Older ComfyUI text widgets do not invoke callback on each keystroke.
        (watched.inputEl || watched.element)?.addEventListener("change", changed);
    }
    refreshCategories();
    node.setSize?.([Math.max(node.size[0], 480), Math.max(node.size[1], 960)]);
}

app.registerExtension({
    name: "DanbooruTagSorter.CategorySelector",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "DanbooruTagSorterNode") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            labelOutputs(this);
            installPanel(this);
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configured?.apply(this, args);
            labelOutputs(this);
            installPanel(this);
            this[PANEL]?.refreshCategories();
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message, ...args) {
            const result = executed?.call(this, message, ...args);
            const payload = message?.category_preview;
            if (Array.isArray(payload)) {
                this[PANEL]?.setPreview(Array.isArray(payload[0]) ? payload[0] : payload);
                this.setDirtyCanvas?.(true, true);
            }
            return result;
        };
        const connections = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = connections?.apply(this, args);
            this[PANEL]?.refreshCategories();
            return result;
        };
    },
});
