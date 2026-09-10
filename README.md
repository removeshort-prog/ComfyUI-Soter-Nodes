<img width="2173" height="1187" alt="例图" src="https://github.com/user-attachments/assets/900ef4a4-74d9-44d0-88eb-4f9a2eb0b290" /># ComfyUI-Soter-Nodes

ComfyUI 的 Danbooru tag 分类节点。将逗号分隔的提示词按数据库分类，在 Packer 内逐项启用、预览和排序，再输出选中的分类数据包与完整文本。

本仓库基于 [RafealaSilva/ComfyUI-Danbooru-Tag-Sorter-Node](https://github.com/RafealaSilva/ComfyUI-Danbooru-Tag-Sorter-Node) 扩展，保留原节点名称及接口。当前改版为本仓库 **2.2.1**，更新记录见 [CHANGELOG](CHANGELOG.md)。

![分类选择器控件预览](<img width="2173" height="1187" alt="例图" src="https://github.com/user-attachments/assets/206da888-54cd-42cd-8c63-fe443740963c" />
)

*上图为实际前端控件在独立浏览器测试页面中的截图，使用示例 tag；不是完整 ComfyUI 工作流运行截图。*

## 安装

在 ComfyUI 的 `custom_nodes` 目录打开终端：

```sh
git clone https://github.com/removeshort-prog/ComfyUI-Soter-Nodes.git
cd ComfyUI-Soter-Nodes
python -m pip install -r requirements.txt
```

这里的 `python` 必须是 **运行 ComfyUI 的 Python**，依赖为 `pandas` 和 `openpyxl`。Windows 官方便携版在上述插件目录中可改用：

```powershell
..\..\..\python_embeded\python.exe -m pip install -r requirements.txt
```

重启 ComfyUI，并刷新浏览器页面。在 `Danbooru Tags` 分类中添加 `Danbooru Tag Sorter (Packer)`。控件随插件加载，无需安装 rgthree。

## 使用分类选择器

1. 在 `tags` 输入框填写或连接逗号分隔的 tag，支持 WD14 等反推节点、Booru Gallery、其他文本节点和手动输入。`excel_file` 默认使用随附的 `danbooru_tags.xlsx`。
2. 原 `new_category_order` 文本框位置显示分类列表：左侧开关控制启用，中间显示分类后的 tag，右侧显示分类名。
3. 使用上下箭头，或拖动右侧分类名调整位置。顶部开关可全部启用或关闭；输出按列表从上到下排列。
4. 运行工作流后查看 tag 预览；点击预览可展开长文本。关闭的分类仍显示预览，便于决定是否启用。预览来自上次运行，修改输入后需再次运行才能更新。
5. 保存工作流即可保存分类顺序和开关状态。开关与排序操作接入 ComfyUI 的撤销/重做事务。
6. 将 **`ALL_TAGS·已选tag`** 输出连接文本预览节点或 CLIP 的文本输入，`is_comment` 选择 **`仅tag`（false）**，即可得到不含分类标题的所选 tag。新建节点默认使用此设置；旧工作流保留原开关值，需手动切换后保存。

新建节点默认显示并启用全部 14 类，顺序为：版权、角色名、画师词、背景词、人物对象词、角色特征词、角色五官词、角色部位词、性征部位词、服饰词、动作词、角色表情词、镜头词、未归类词。

`category_mapping` 中的全部目标分类和 `default_category` 都会出现在列表中。读取旧配置或新增映射时，未列出的分类会追加到末尾，默认关闭，需主动开启。默认分类也可以移动；未匹配的 tag 在该行位置输出，关闭该行后不输出。

### 输出与配套节点

| 节点 / 输出 | 行为 |
| --- | --- |
| Packer → `分类数据包·Getter` (`TAG_BUNDLE`) | 供 Getter 提取分类的结构化字典，按列表顺序保存已启用分类。已启用但没有 tag 的分类保留为空字符串；关闭项不会出现在字典中。不要直接连接最终提示词。 |
| Packer → `ALL_TAGS·已选tag` (`STRING`) | 供文本预览或 CLIP 使用，按相同顺序拼接已启用分类的非空 tag。`is_comment` 默认 `仅tag`（false）；选择 `含分类名`（true）时添加分类标题。 |
| `Danbooru Tag Getter (Extractor)` | 连接分类数据包，在 `category_name` 填写分类名，返回对应文本；不存在或已关闭的分类返回空字符串。 |
| `Danbooru Tag Clear Cache` | 清除数据库、离线名称索引和在线查询缓存；也可在 Packer 开启 `force_reload` 重新读取、查询。 |

关闭某个分类时，其中的 tag 会从两个输出中排除，**不会转入“未归类词”**。全部关闭时输出空字典和空字符串。分类内部保持数据库顺序，未匹配的 tag 保持输入顺序；黑名单、正则过滤和去重同时作用于输出与预览。

例如将“镜头词”移到“角色特征词”前，并关闭“角色表情词”，输出就先包含镜头，再包含角色特征，表情 tag 不进入数据包或 `ALL_TAGS`。

仅启用“人物对象词”和“镜头词”，按此顺序排列，`ALL_TAGS·已选tag` 在 `仅tag` 模式下的示例输出为：

```text
1girl, bare_legs,
solo, full_body, foreshortening, foot_focus,
```

这里没有分类名、JSON 花括号或编码转义。tag 自身原有的括号等字符会保留。

如果“预览任意”等通用预览节点显示 `\u955c\u5934\u8bcd`、花括号和引号，检查是否接到了**分类数据包**：这是预览节点把字典转为 JSON 时对中文分类名“镜头词”的转义显示，并非分类器额外插入的 tag。改接 **`ALL_TAGS·已选tag`** 并选择 **`仅tag`**，重新运行即可。输出的新标签用于区分用途，原有插槽名称、顺序和类型保持兼容。

### 版权与角色名

选择器支持 Danbooru 的版权和角色分类，例如 `arknights` 归入“版权”，`suzuran_(arknights)`、`vulpisfoglia_(arknights)` 归入“角色名”。两类都支持开关和排序，原始 tag 拼写及角色名中的括号保持不变。

已有工作流会自动补齐缺失的版权、角色名映射，无需重置原有 `category_mapping`；显式设置的自定义映射优先。旧面板中新补入的两行默认关闭，请手动开启并安排输出位置，再保存工作流。

插件随附 **73,171** 个规范名称的离线索引，包含 **12,728** 个版权名、**60,443** 个角色名，按 Danbooru 类别 `3` / `4` 区分，不根据括号或后缀猜测。索引取自 2026-04-01、最低 post count 为 20 的快照，来源、授权和重建方式见 [分类数据说明](tags_database/NAMED_CATEGORIES.md)。

`danbooru_lookup` 默认开启，开关显示为 **`补查 D 站分类`** / **`仅本地分类`**。本地数据库和离线索引仍未识别的 tag，会通过 [Danbooru 标签接口](https://danbooru.donmai.us/tags.json) 补查版权与角色类别；黑名单过滤项及已有明确映射不送去补查。成功识别的结果在当前 ComfyUI 进程中缓存 24 小时；成功查询但不属于这两类或未找到的结果缓存 1 小时。查询超时或失败时记录警告，相关 tag 按默认分类处理，工作流继续运行，下次执行可重试。切换为 `仅本地分类` 可关闭在线补查；需要重新查询时使用 `force_reload` 或清缓存节点。

使用 **Aaalice Booru Gallery** 时，将其 `prompts` 输出直接连接 Packer 的 `tags` 输入，再从 `ALL_TAGS·已选tag` 输出到预览或 CLIP，无需修改 Gallery 或增加连线。直接连接且能匹配当前图片提示词时，Packer 会读取 Gallery 保存的分类数据，优先复用其中的版权、角色等已知类别，以实际选择、排除和编辑后的 tag 为准；多张图片分别匹配，不混用分类。

分类优先级为：显式自定义映射 → 当前 Gallery 图片的分类 → 本地离线分类 → 可选 D 站补查。连接其他节点、缺少 Gallery 数据或无法可靠匹配时，继续使用本地分类和在线补查。Gallery 将下划线换成空格，或把括号转义成 `\(` / `\)` 时，仍可匹配分类；这些处理仅用于查找，输出保留输入 tag 的原始拼写。

在线缓存过期和失败重试会在 Packer 实际执行时检查。相同输入重复运行可能直接使用 ComfyUI 的执行缓存；需要立即重查时，切换 `force_reload` 为 true 后运行，完成后改回 false。

反推和手动输入不需要 Gallery：直接将 tag 文本接入 `tags`，即可使用同一套分类、开关、排序和纯文本输出。Gallery 快照只是可选的分类信息来源。

## 配置与旧工作流

- `tags_database/danbooru_tags.xlsx` 是内置数据库。`excel_file` 可填该目录中的文件名，或自定义数据库的绝对路径；支持 Excel / CSV，需包含 `english`、`category`、`subcategory` 列。
- `defaults_config.json` 定义新建节点的映射和初始顺序；修改后重启 ComfyUI。已有节点保留工作流内保存的配置。
- 升级后，已有工作流中的 `is_comment` 和输出连线不会自动改变。要只输出 tag，请手动选择 `仅tag`（false），并将预览或提示词连线改接 `ALL_TAGS·已选tag`。
- `category_mapping` 沿用原字典格式，例如 `{('人物', '眼睛'): '角色特征词'}`，可按数据库的大类、小类重新组合分类。
- 版权和角色名使用 `('版权', '作品')`、`('角色', '角色名')` 两个映射键，缺失时分别映射到“版权”和“角色名”。
- `new_category_order` 仍为 `STRING` 输入。新面板保存以下 JSON，数组顺序即输出顺序：

```json
[
  {"name": "镜头词", "enabled": true},
  {"name": "角色特征词", "enabled": true},
  {"name": "角色表情词", "enabled": false},
  {"name": "未归类词", "enabled": false}
]
```

对象数组中未列出的映射分类会补齐为关闭项。`enabled` 应为 JSON 布尔值 `true` / `false`。

旧工作流的分类名称数组（如 `["角色特征词", "未归类词"]`）可直接读取；面板将原有名称转为启用项，补齐遗漏分类为关闭项，并保持其他控件的保存位置。通过 API 直接提交旧名称数组时仍沿用原行为：未列出的映射分类由 `validation` 校验；关闭校验时归入默认分类，Python 调用仍返回原二元组。对象数组模式通过 ComfyUI 的 `ui` / `result` 返回预览及结果，输出插槽类型不变。

如果 `new_category_order` 已转换为输入并连接上游，分类选择和顺序由上游提供，本地面板进入只读预览状态。断开后恢复本地保存的选择。

### 从原插件迁移

1. 备份工作流、原插件的 `defaults_config.json` 和 `tags_database`，以及使用中的外部数据库。
2. 关闭 ComfyUI，将原 `ComfyUI-Danbooru-Tag-Sorter-Node` 文件夹移出 `custom_nodes`，再安装本仓库。两者注册相同节点名，避免同时加载；只改文件夹名称不能防止重复加载。
3. 按需恢复自定义配置和数据库。重新打开旧工作流，检查 `excel_file` 是否仍指向有效路径；使用内置库时填 `danbooru_tags.xlsx`。
4. 重启 ComfyUI，强制刷新浏览器，再确认分类开关与顺序并保存工作流。

原有 Packer、Getter、Clear Cache 节点及连线可继续使用。迁移后可用全开、部分关闭和全关各运行一次，核对实际输出。

[示例工作流](example/Workflow.json) 包含 [ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) 的文本预览节点，导入完整示例需安装该依赖；本插件自身不依赖它，也可自行连接可用的文本显示节点。

## 测试

在插件目录执行，Python 环境先安装 `requirements.txt`：

```sh
python -m unittest discover -s tests -v
```

前端测试需要 Node.js 20+、Playwright 和可启动的 Chromium：

```sh
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node --test tests/frontend.test.mjs
```

如果已有环境，可通过 `PLAYWRIGHT_MODULE` 指定可解析的 Playwright 模块路径，通过 `CHROME_EXECUTABLE` 指定 Chrome / Chromium 可执行文件路径；使用现有浏览器时无需下载 Chromium。这些依赖仅用于开发测试，不是 ComfyUI 运行依赖。

本次验证通过 **59 项 Python 测试、15 项浏览器交互场景**（Node TAP 汇总含父测试为 16 项），覆盖启用过滤、顺序、纯 tag 输出、版权与角色名、反推输入、Gallery 分类匹配及多图隔离、在线补查与缓存、Getter、拖动、键盘操作、工作流恢复、连线模式和撤销事务。另已实际加载随附 Excel，索引 **221,784** 个 tag，并核对离线名称分类；Gallery 提示词重建逻辑与上游 `compose_prompt` 对照 **100 组组合**，结果一致。

浏览器测试运行真实前端控件，但 ComfyUI 的节点、图和事件接口由测试替身提供；用户已反馈分类选择器可用，本次完整改动仍需在实际 ComfyUI 环境验证。在线补查测试使用模拟的 Danbooru 接口响应；开发环境直连该接口超时，未完成真实在线查询验证。试用反馈请附 ComfyUI / 前端版本、复现步骤和相关报错。

## 来源与许可

原作者：[RafealaSilva](https://github.com/RafealaSilva)。本次基于上游提交 [`8957613`](https://github.com/RafealaSilva/ComfyUI-Danbooru-Tag-Sorter-Node/commit/8957613905488033f8297e246c5e1adfbe387560) 扩展分类选择器；本仓库版本号不代表上游官方发布。

沿用 [MIT License](LICENSE)，保留原作者版权声明。
