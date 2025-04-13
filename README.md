## 子仓库下载和打包命令

### 下载子仓库

```bash
git submodule update --init --recursive
```

### 更新子仓库

```bash
git submodule update --remote
```

### 切换子仓库到 master 分支并拉取最新代码

```bash
# 进入子仓库目录
cd frontend
# 拉取最新代码
git pull origin master

# 切换到 master 分支
git checkout master


```

### 打包命令

```bash
# 进入子仓库目录
cd frontend

# 下载依赖包
pnpm install

# 执行打包
pnpm run build-only
```
