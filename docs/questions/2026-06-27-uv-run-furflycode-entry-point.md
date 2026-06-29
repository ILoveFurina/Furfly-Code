---
status: answered
tags: [build, pyproject, uv, entry-point]
created: 2026-06-27
answered: 2026-06-27
related:
  - 2026-06-27-backend-tui-decoupling-points.md
---

# 为什么一句 `uv run furflycode` 就能启动项目？

## 背景

刚开始接触项目，看到 CLAUDE.md 里写 `uv run furflycode` 或 `uv run python -m furflycode` 都能跑，
但没想清楚 `uv` 是怎么知道 `furflycode` 是一个可执行命令的——毕竟 `src/` 下并没有
生成任何 `bin/furflycode` 脚本。

## 当时的想法

- 猜是 `pyproject.toml` 里有什么 `[scripts]` 之类的配置。
- 以为 `uv run furflycode` 是先去找 PATH 里的可执行文件，找不到就报错。

## 解答

关键在 `pyproject.toml:14-15` 的 `[project.scripts]`：

```toml
[project.scripts]
furflycode = "furflycode.cli:main"
```

这一行做了三件事：

1. **声明命令名** —— `furflycode` 就是用户敲的命令。
2. **绑定到 Python 函数** —— `furflycode.cli:main` 指 `cli.py` 里的 `main()`。
3. **让构建系统知道要生成 console script 入口** —— `hatchling` 构建后会在虚拟环境里
   生成一个 `furflycode` 可执行 wrapper，它实际就是 import + 调 `main()`。

`uv run furflycode` 的执行链路：

```
uv run furflycode
   │
   ├── 1. 自动同步依赖（按 pyproject.toml 的 dependencies）
   ├── 2. 在项目虚拟环境里查找 [project.scripts] 注册的 furflycode 入口
   └── 3. 执行该入口 → import furflycode.cli → main()
                                       ├── load(".furflycode/config.yaml")
                                       └── furflycodeApp(config.providers).run()
```

`uv run python -m furflycode` 走的是另一条路——找包里的 `__main__.py` 执行。两条路最终汇到 TUI。

## 决策

不需要改动项目。这是标准的 PEP 621 入口脚本声明。

## 参考

- `pyproject.toml:14-15`：`[project.scripts]` 声明
- `src/furflycode/cli.py:11`：`main()` 入口
- `src/furflycode/__main__.py`：`python -m furflycode` 的入口