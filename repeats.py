"""反复段解析与展开核心逻辑。

输入格式（逐行）：
    [|:]小节编号[:|xN]
- 编号前的 |:     表示反复起点
- 编号后的 :|xN   表示反复终点，N 为重复次数（2~9）
- 反复段允许嵌套
"""

import re

# 展开小节数上限
MAX_MEASURES = 5000

# 行格式：可选的 |: 前缀 + 编号 + 可选的 :|xN 后缀（N 为 2~9）
LINE_RE = re.compile(r"^\s*(?:(\|:)\s*)?(\d+)(?:\s*(:\|)\s*[xX]\s*([2-9]))?\s*$")

FORMAT_HINT = "格式错误：应为 [|:]编号[:|xN]，N 为 2~9，例如 “|:12:|x3”"


def parse(text):
    """解析输入文本，构建嵌套树并校验。

    返回 (root, errors)：
    - root  为 {"type": "group", "count": 1, "children": [...]} 形式的根节点；
      小节节点为 {"type": "measure", "num": 编号, "line": 行号}。
    - errors 为 [{"line": 行号, "message": 错误描述}, ...]，按行号排序。
    """
    errors = []
    root = {"type": "group", "count": 1, "children": [], "line": None}
    stack = [root]  # 当前嵌套层级的分组栈，栈底为根
    seen = {}  # 小节编号 -> 首次出现的行号

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue  # 跳过空行

        m = LINE_RE.match(raw)
        if not m:
            errors.append({"line": lineno, "message": FORMAT_HINT})
            continue

        start, num_s, _end, count_s = m.groups()
        num = int(num_s)

        # 编号唯一性校验
        if num in seen:
            errors.append({
                "line": lineno,
                "message": f"小节编号 {num} 重复，首次出现在第 {seen[num]} 行",
            })
        else:
            seen[num] = lineno

        # 反复起点：新建分组并压栈，本行小节属于该分组
        if start:
            group = {"type": "group", "count": None, "children": [], "line": lineno}
            stack[-1]["children"].append(group)
            stack.append(group)

        stack[-1]["children"].append(
            {"type": "measure", "num": num, "line": lineno}
        )

        # 反复终点：弹出当前分组并记录重复次数
        if count_s is not None:
            if len(stack) == 1:
                errors.append({
                    "line": lineno,
                    "message": "反复终点 :| 没有匹配的反复起点 |:",
                })
            else:
                group = stack.pop()
                group["count"] = int(count_s)
                group["end_line"] = lineno

    # 输入结束时仍未闭合的反复起点
    while len(stack) > 1:
        group = stack.pop()
        errors.append({
            "line": group["line"],
            "message": "反复起点 |: 没有匹配的反复终点 :|xN",
        })

    errors.sort(key=lambda e: e["line"])
    return root, errors


def expand(root, limit=MAX_MEASURES):
    """按嵌套层级展开为实际演奏顺序（迭代实现，避免深嵌套递归溢出）。

    返回 (rows, overflow)：
    - rows     为 [{"seq": 演奏序号, "num": 原小节编号, "line": 源行号}, ...]
    - overflow 为导致超过 limit 的小节节点；未超限时为 None
    """
    rows = []
    # 帧结构：[子节点列表, 下一个待处理下标, 剩余重复次数]
    stack = [[root["children"], 0, 1]]
    while stack:
        frame = stack[-1]
        children, idx, _ = frame
        if idx >= len(children):
            # 当前分组一轮结束：剩余次数减一后从头再来
            stack.pop()
            frame[2] -= 1
            if frame[2] > 0:
                frame[1] = 0
                stack.append(frame)
            continue
        node = children[idx]
        frame[1] += 1
        if node["type"] == "measure":
            rows.append({"seq": len(rows) + 1, "num": node["num"], "line": node["line"]})
            if len(rows) > limit:
                return rows, node
        else:
            stack.append([node["children"], 0, node["count"]])
    return rows, None
