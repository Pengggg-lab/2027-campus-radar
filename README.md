# 2027届秋招雷达

一个面向 2027 届硕士秋招的移动端网页。它从你提供的《央企及川渝国企校招信息汇总.xlsx》读取 192 家企业，保留企业官网和网申链接，并每天扫描官方招聘页面后更新状态。

## 页面能做什么

- 区分央企、四川、重庆、贵州四个范围。
- 展示“已发现 2027 校招”“今日更新”“年份待核实”“暂未发现”“访问异常”五类状态。
- 支持搜索、状态筛选和地区筛选。
- 每家企业可直接跳转网申页或企业官网；扫描时提取到的职位、公告链接也会显示在卡片上。
- 手机浏览器可直接访问，也可添加到手机桌面。

公开网页不会显示 Excel 里个人填写的“已投递/不投递”字段。

## 状态怎么判定

脚本只根据官方页面中的文字证据判断：

- **已发现 2027 校招**：页面同时出现 2027 届/2027 年度等年份词和校园招聘/校招/网申等词。
- **今日更新**：当天日期附近同时出现校招词。它表示“页面今天出现相关日期”，不代表岗位一定是今天首次发布。
- **年份待核实**：找到校招入口，但没有读到 2027 届证据。
- **暂未发现**：本次扫描没有读到 2027 校招证据。它**不等于**企业确定未发布，也不排除子公司单独发布。
- **访问异常**：验证码、地区网络限制、超时或动态页面无法核验。

招聘网站结构、验证码和网络出口会影响结果。任何重要岗位都应点击卡片里的官网链接再次确认。

## 远程访问和每天 14:00 更新

项目包含 GitHub Actions 工作流：

- `06:00 UTC`（北京时间 `14:00`）自动运行。
- 工作流先读取 Excel，再扫描招聘门户，并复核企业官网公告与总部动态。
- 更新后的 `site/data/companies.json` 会提交回仓库。
- 静态页面自动发布到 GitHub Pages，手机通过 Pages 网址访问。

由于当前项目不是已登录的 GitHub 仓库，需要你在 GitHub 上做一次首次发布：

1. 在 GitHub 新建一个仓库，建议设为 Public。网页不包含个人投递状态，Public 仓库可以直接使用免费的 Pages。
2. 在本目录执行（把网址换成你的空仓库地址）：

```powershell
.\首次发布到GitHub.ps1 -RepositoryUrl "https://github.com/你的用户名/仓库名.git"
```

也可以手动执行：

```powershell
git init
git add .
git commit -m "init: 2027 campus radar"
git branch -M main
git remote add origin https://github.com/你的用户名/仓库名.git
git push -u origin main
```

3. 打开仓库 `Settings` → `Pages` → `Build and deployment`，把 Source 设为 `GitHub Actions`。
4. 打开仓库 `Actions`，选择“更新招聘数据并发布网页”，点一次 `Run workflow`。
5. 首次运行完成后，页面地址通常为：

```text
https://你的用户名.github.io/仓库名/
```

在手机上打开该网址后，可用浏览器菜单里的“添加到主屏幕”。

> GitHub 的定时任务可能排队延迟几分钟。仓库连续 60 天没有活动时，GitHub 可能暂停定时任务；本项目每天会提交数据更新，所以正常情况下会保持运行。

## 本地预览

```powershell
python -m http.server 8080 --directory site
```

浏览器打开 `http://localhost:8080/`。手机与电脑在同一 Wi-Fi 时，也可以访问电脑的局域网 IP 加 `:8080`，但这不是稳定的远程方案。

## 手动更新数据

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python scripts/build_companies.py --source data/source.xlsx --output site/data/companies.json --previous site/data/companies.json
python scripts/scan_jobs.py --browser auto --concurrency 6
python scripts/scan_jobs.py --browser auto --url-field official --statuses possible not_found error not_checked --keep-stronger --concurrency 6
```

更新企业名单时，直接替换 `data/source.xlsx`，保持四个工作表名称和现有表头结构即可。重新执行上面的 `build_companies.py` 会覆盖公开企业列表，同时保留已有扫描结果。

## 文件说明

```text
site/                        可直接发布的静态网页
site/data/companies.json     企业名单和最近一次扫描结果
scripts/build_companies.py   从 Excel 重建名单
scripts/scan_jobs.py         官网招聘信息扫描器
data/source.xlsx             原始企业名单
data/overrides.json          个别企业链接修订
.github/workflows/           每天 14:00 更新并发布
```
