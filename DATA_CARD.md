# DATA CARD · 紫微斗数白话知识库（zeropro_open_kb.json）

- 内容：紫微斗数白话知识切片，覆盖十二宫星系、格局、四化等主题
- 规模：4253 片
- 文件：data/zeropro_open_kb.json（JSON 数组，UTF-8）
- 许可：CC BY-SA 4.0（全文见 DATASET-LICENSE）

## 字段 schema
| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 切片唯一标识 |
| topic / parent_topic | string | 主题 / 父级主题（检索路由字段） |
| content | string | 白话正文 |
| classics_ref | string | 公有领域古籍出处（空=无） |
| tags | list[string] | 标签 |
| related_palaces / related_stars / related_sihua | list[string] | 关联宫位 / 星曜 / 四化 |
| pattern_type | string | 象别类型 |
| confidence | string | 置信标注 |
| char_count | int | 正文字符数 |
| source / source_type | string | 来源 / 来源类型（zeropro） |
| author / school | string | 署名 / 流派归属 |
| is_classical / is_sutra | bool | 古籍 / 经典标记（个别片为 is_sutras 拼写变体，语义相同） |
| palace | string | 宫位标注（极少数通论片携带，常为空） |
