# 版权与角色名分类数据

`named_categories.json` 是运行时使用的离线名称索引，用于区分 Excel 中混在“二次元角色”大类里的作品名和角色名，也能识别本索引中已有、Excel 中尚未收录的名称。分类取自 Danbooru 的数字类别，不根据括号或后缀推测。

## 来源与范围

- 数据整理者：[DraconicDragon / dbr-e621-lists-archive](https://github.com/DraconicDragon/dbr-e621-lists-archive)。
- 固定提交：[`e67f8782c80857e99804d2afd7677cb5837a34ee`](https://github.com/DraconicDragon/dbr-e621-lists-archive/commit/e67f8782c80857e99804d2afd7677cb5837a34ee)。
- 源文件：[danbooru_2026-04-01_pt20-ia-dd.csv](https://github.com/DraconicDragon/dbr-e621-lists-archive/blob/e67f8782c80857e99804d2afd7677cb5837a34ee/tag-lists/danbooru/danbooru_2026-04-01_pt20-ia-dd.csv)。
- 快照日期：2026-04-01；源文件最低 post count 为 20，共 201,269 行。
- 仅提取数字类别 `3`（copyright，版权）和 `4`（character，角色名）的规范名称，分别为 **12,728** 和 **60,443** 个，共 **73,171** 个。别名列、出现次数和其他类别不打包。
- 所有名称去重后按字符串排序。本文件提供离线查表；节点另有默认开启的 `danbooru_lookup`，可对本地资料未能明确区分的名称查询公开 Danbooru API。关闭查询或查询失败时继续使用现有 Excel 和未归类规则。
- 核对示例：`arknights` 为版权；`suzuran_(arknights)`、`vulpisfoglia_(arknights)` 为角色名。`character_name` 和 `infection_monitor_(arknights)` 在源文件中是通用类别 `0`，不收进这两个类别。

这是一份有限时间点、带收录阈值的快照，不保证覆盖全部新角色和低频名称。源文件中的规范名称按原样保存；输入 tag 的文本形式仍由节点保持。

## 重建方法

下载上述固定提交的 CSV 到仓库外的临时目录，然后在仓库根目录执行：

```bash
python scripts/update_named_categories.py /path/to/danbooru_2026-04-01_pt20-ia-dd.csv
```

脚本只使用 Python 标准库，校验源文件后生成 `tags_database/named_categories.json`。源 CSV 不随插件分发；运行节点无需下载本快照。可选的在线查询只发送待识别名称，不下载整个数据库。

源文件 SHA-256：

```text
175d0a30f260318fedef95d7ce9b1f250dda89ea55e437c0a6c3b7571bb91e34
```

更新快照时，核对新源文件的日期、类别列与授权，使用 `--sha256 NEW_SHA256`，同时更新本文的固定来源、校验和及数量。不要使用推测规则填充尚未收录的名称。

## 上游授权

数据源仓库以 [The Unlicense](https://github.com/DraconicDragon/dbr-e621-lists-archive/blob/e67f8782c80857e99804d2afd7677cb5837a34ee/LICENSE) 发布。以下保留其声明；插件原有 MIT 许可证不变。

```text
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org>
```
