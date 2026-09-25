# 乐谱反复段展开工具

供排练使用的 Web 应用：逐行输入小节编号与反复记号，自动校验并展开为实际演奏顺序，
页面展示演奏序号、原小节编号和源行号，并可下载同内容的 CSV。

## 启动

```bash
docker compose up --build
```

容器启动时会自动安装依赖（`pip install -r requirements.txt`）并启动应用。

## 访问

浏览器打开 <http://localhost:5000>

## 配置

| 环境变量 | 默认值 | 说明 |
| -------- | ------ | ---- |
| `PORT`   | `5000` | 应用监听端口（修改后请同步调整 compose 的端口映射） |

## 输入格式

每行一个小节编号：

- 编号前加 `|:` 表示反复起点
- 编号后加 `:|xN` 表示反复终点，`N` 为重复次数（2~9）
- 反复段允许嵌套；空行会被忽略

示例：

```
1
2
|:3
4
|:5
6:|x3
7:|x2
8
```

展开结果：`1 2 3 4 5 6 5 6 5 6 7 3 4 5 6 5 6 5 6 7 8`（共 21 小节）。

## 校验规则

- 格式错误：定位到具体输入行
- 小节编号必须唯一，重复时指出首次出现的行号
- `|:` 与 `:|xN` 必须配对，未配对时定位到对应行
- 展开超过 5000 小节时停止，并指出导致超限的源行

## 本地开发（不使用 Docker）

```bash
pip install -r requirements.txt
python app.py
```

## 项目结构

```
app.py               Flask 应用与 API
repeats.py           反复段解析、校验与展开逻辑
templates/index.html 前端页面（原生 HTML/JavaScript）
requirements.txt     Python 依赖
Dockerfile           镜像构建（依赖随容器启动安装）
docker-compose.yml   Compose 编排
```
