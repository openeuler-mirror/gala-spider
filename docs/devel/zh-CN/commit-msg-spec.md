# Git Commit Message 提交规范

每次通过 Git 提交代码时，都需要通过 `git commit` 命令填写提交说明（Commit Message）。为了规范化提交说明，我们使用统一的[约定式提交规范](https://www.conventionalcommits.org/zh-hans/v1.0.0/)，并通过 **gitlint** 自动化工具对提交说明进行本地校验。

## gitlint使用说明

1. 下载 gitlint 到本地

   ```shell
   pip install gitlint
   ```

   > 说明：使用 gitlint 需要本地支持 python 运行环境；下载时若默认的 pip 源无法访问，需要配置可访问的 pip 源。

2. 配置提交规范

   将你的远程 git 项目克隆到本地后，进入项目根目录下，如果不存在 `.gitlint` 配置文件，则添加一个，配置内容如下：

   ```ini
   [general]
   # Ignore certain rules, this example uses both full name and id
   ignore=body-is-missing, T3
   
   # Enable community contributed rules
   # See http://jorisroovers.github.io/gitlint/contrib_rules for details
   contrib=contrib-title-conventional-commits
   ```

   其中，配置项 `contrib=contrib-title-conventional-commits` 表示使用约定式提交规范来进行提交校验。

   > 说明：配置好 `.gitlint` 文件后，将其提交到远程仓库，后面可直接使用。

3. 开启提交校验功能

   将你的远程 git 项目克隆到本地后，进入项目根目录下，执行：

   ```shell
   gitlint install-hook
   ```

   该命令会在本地 git 项目的 `.git/hook/` 目录下生成一个 `commit-msg` 钩子脚本，它的作用是：每当我们通过 `git commit` 填写提交说明后，会触发 `commit-msg` 钩子脚本的执行，它会对提交的内容进行校验。如果校验不通过，将会打印提示信息，并放弃本次提交。

   > 说明：
   >
   > 1. 只有第一次克隆 git 项目到本地后，才需要执行 `gitlint install-hook` 命令，之后会一直生效。
   > 2. 生成的 `.git/hook/commit-msg` 文件只会在本地保存，不会提交到远程仓库。
   > 3. 如果需要关闭该校验功能，执行 `gitlint uninstall-hook` 删除 `commit-msg` 钩子脚本即可。

4. 效果展示

   提交一个不满足规范的提交说明，

   ```shell
   # ~ MINGW64 /d/workspace/gala-spider (master)
   git commit -m "add gitlint config"
   # gitlint: checking commit message...
   # 1: CT1 Title does not follow ConventionalCommits.org format 'type(optional-scope): description': "add gitlint config"
   # -----------------------------------------------
   # gitlint: Your commit message contains violations.
   # Continue with commit anyways (this keeps the current commit message)? [y(es)/n(no)/e(dit)] n
   # Commit aborted.
   # Your commit message:
   # -----------------------------------------------
   # add gitlint config
   # -----------------------------------------------
   ```

   提交一个满足规范的提交说明，

   ```shell
   # ~ MINGW64 /d/workspace/gala-spider (master)
   git commit -m "feat: add gitlint config"
   # gitlint: checking commit message...
   # gitlint: OK (no violations in commit message)
   # [master 9cfaa99] feat: add gitlint config
   #  1 file changed, 7 insertions(+)
   #  create mode 100644 .gitlint
   ```

## 约定式提交规范

约定式提交规范是一种基于提交信息的轻量级约定。 它提供了一组简单规则来创建清晰的提交历史； 这更有利于编写自动化工具。

下面对常用的约定式提交规范进行说明，更多详细的信息参加官方文档：[约定式提交](https://www.conventionalcommits.org/zh-hans/v1.0.0/) 。

Commit Message 的格式如下：

```
<type>[(optional scope)]: <description>

[optional body]

[optional footer(s)]
```

它包括三个部分：Header（第一行），Body 和 Footer。其中，Header 是**必需**的，Body 和 Footer 是**可选**的。

### Header

Header 部分只有一行，包括三个字段：**type**（必需）、**scope**（可选）和 **description**（必需）。

**type**

type 表示本次提交的类型，它的取值主要包括：

- **feat**：表示在代码库中新增了一个功能（feature）。
- **fix**：表示在代码库中修复了一个 bug 。
- **docs**：文档修改。
- **refactor**：表示对代码进行了重构，而不是新增功能或修复 bug 。
- **test**：添加或修改测试用例。
- **ci**：对 CI 配置文件和脚本的更改。
- **style**：不影响代码含义的更改（空格、格式、缺少分号等）。
- ……

**scope**

scope 用于说明本次提交影响的范围，它是一个描述某部分代码的名词，并用圆括号包围，例如：`fix(config):`。

**description**

description 是对本次提交的简单描述，它直接跟在 `type(scope):` 后面，并与冒号之间**必须**有一个空格。

### Body

在简短描述之后，可以编写较长的提交正文 Body，为代码变更提供额外的上下文信息。

- 正文**必须**与 Header 之间空一行。
- 提交的正文内容自由编写，并可以使用空行分隔不同段落。

### Footer

在正文结束的一个空行之后，可以编写一行或多行脚注。

- 每行脚注都**必须**包含 一个令牌（token），后面紧跟 `:<space>` 或 `<space>#` 作为分隔符，后面再紧跟令牌的值（受 [git trailer convention](https://git-scm.com/docs/git-interpret-trailers) 启发）。
- 脚注的令牌**必须**使用 `-` 作为连字符，比如 `Acked-by`。有一种例外情况就是 `BREAKING CHANGE`，它可以被认为是一个令牌。
- 在脚注中包含 `BREAKING CHANGE:`，表示引入了破坏性 API 变更。

例，一个包含多行正文和多行脚注的提交说明如下：

```
fix: prevent racing of requests

Introduce a request id and a reference to latest request. Dismiss
incoming responses other than from latest request.

Remove timeouts which were used to mitigate the racing issue but are
obsolete now.

Reviewed-by: Z
Refs: #123
```

